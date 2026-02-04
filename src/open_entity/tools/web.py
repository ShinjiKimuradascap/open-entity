# -*- coding: utf-8 -*-
"""
Web関連ツール - Gemini Grounding ベース

BeautifulSoup や Google Custom Search API を使わず、
Gemini の Google Search Grounding 機能で Web 検索を実行
"""
import html
import os
import re
import socket
import ipaddress
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import List, Optional

from open_entity.core.llm_provider import generate_text, get_preferred_provider, get_analyzer_model

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    genai = None
    types = None
    HAS_GENAI = False

USER_AGENT = "Mozilla/5.0 (compatible; open-entity/1.0; +https://open-entity)"
MAX_RESULTS = 5
MAX_FETCH_CHARS = 12000
MAX_FETCH_BYTES = 2 * 1024 * 1024


def _has_gemini_key() -> bool:
    return bool(
        os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    )


def _is_private_url(url: str) -> bool:
    """URLがプライベートIP/localhostを指しているか判定（SSRF対策）"""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            try:
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
                return ip.is_private or ip.is_loopback or ip.is_reserved
            except socket.gaierror:
                return False
    except Exception:
        return True


def _is_http_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl:
            return None
        if not _is_http_url(newurl):
            raise ValueError("Unsupported URL scheme")
        if _is_private_url(newurl):
            raise ValueError("Access to private/internal URLs is not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_url(url: str, timeout: int = 20, max_bytes: int = MAX_FETCH_BYTES) -> tuple[str, str, bool]:
    """URLを取得して (text, content_type, truncated) を返す。"""
    if not _is_http_url(url):
        raise ValueError("Only http/https URLs are supported")
    if _is_private_url(url):
        raise ValueError("Access to private/internal URLs is not allowed")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    with opener.open(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        chunks = []
        total = 0
        truncated = False
        while True:
            read_size = min(65536, max_bytes - total)
            if read_size <= 0:
                truncated = True
                break
            chunk = response.read(read_size)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                truncated = True
                break
        raw = b"".join(chunks)

    charset_match = re.search(r"charset=([^;]+)", content_type, re.IGNORECASE)
    charset = charset_match.group(1).strip() if charset_match else "utf-8"
    text = raw.decode(charset, errors="ignore")
    return text, content_type, truncated


def _strip_html(html_text: str) -> str:
    """HTMLを簡易的にテキスト化"""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _decode_ddg_url(url: str) -> str:
    """DuckDuckGoのリダイレクトURLを復号"""
    if "duckduckgo.com/l/?" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return urllib.parse.unquote(qs["uddg"][0])
    if url.startswith("//"):
        return "https:" + url
    return url


class _DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: List[dict] = []
        self._current = None
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "class" in attrs and "result__a" in attrs["class"]:
            if self._current:
                self.results.append(self._current)
            self._current = {
                "title": "",
                "url": _decode_ddg_url(attrs.get("href", "")),
                "snippet": "",
            }
            self._in_title = True
        elif tag in ("a", "div") and "class" in attrs and "result__snippet" in attrs["class"]:
            if self._current:
                self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
        if tag in ("a", "div") and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_title and self._current is not None:
            self._current["title"] += data
        elif self._in_snippet and self._current is not None:
            self._current["snippet"] += data

    def close(self):
        super().close()
        if self._current:
            self.results.append(self._current)
            self._current = None


def _search_duckduckgo(query: str, max_results: int = MAX_RESULTS) -> List[dict]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    html_text, _, _ = _fetch_url(url)
    parser = _DuckDuckGoParser()
    parser.feed(html_text)
    parser.close()
    results = []
    seen = set()
    for item in parser.results:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "title": title,
            "url": url,
            "snippet": (item.get("snippet") or "").strip(),
        })
        if len(results) >= max_results:
            break
    return results


def _summarize_search_results(query: str, results: List[dict]) -> str:
    sources = []
    for idx, r in enumerate(results, 1):
        snippet = r.get("snippet", "")
        sources.append(
            f"[{idx}] {r.get('title','')}\nURL: {r.get('url','')}\nSnippet: {snippet}"
        )
    sources_text = "\n\n".join(sources)

    prompt = f"""次の検索結果に基づいて質問に答えてください。
情報が不足する場合は「不明」と明記してください。
可能なら回答中に [1] [2] のような参照番号を付けてください。

質問:
{query}

検索結果:
{sources_text}
"""
    provider = get_preferred_provider()
    model = get_analyzer_model(provider)
    return generate_text(prompt=prompt, provider=provider, model=model, temperature=0.2, max_tokens=800)


def websearch(query: str, site_filter: Optional[str] = None) -> str:
    """
    Gemini の Google Search Grounding を使用して Web 検索を実行します。

    Args:
        query: 検索クエリ
        site_filter: 検索を制限するドメイン (例: "nta.go.jp")

    Returns:
        検索結果を含む回答（参照元 URL 付き）
    """
    use_gemini = HAS_GENAI and _has_gemini_key()

    # サイト制限がある場合、クエリを修正
    search_query = query
    if site_filter:
        search_query = f"site:{site_filter} {query}"

    if use_gemini:
        api_key = os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        try:
            client = genai.Client(api_key=api_key)

            # Google Search Grounding を有効にして生成
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=search_query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            result_parts = []

            # メイン回答
            result_parts.append(response.text)

            # 参照元 URL を抽出
            sources = _extract_grounding_sources(response)
            if sources:
                result_parts.append("\n\n📚 参照元:")
                for source in sources[:MAX_RESULTS]:
                    result_parts.append(f"  - {source['title']}: {source['url']}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error: Web検索に失敗しました (Gemini): {e}"

    # Fallback: DuckDuckGo HTML + LLM summary
    try:
        results = _search_duckduckgo(search_query, max_results=MAX_RESULTS)
        if not results:
            return "Error: 検索結果が取得できませんでした。"
        try:
            answer = _summarize_search_results(query, results)
            sources = "\n".join([f"  - {r['title']}: {r['url']}" for r in results])
            return f"{answer}\n\n📚 参照元:\n{sources}"
        except Exception:
            sources = "\n".join([f"  - {r['title']}: {r['url']}" for r in results])
            return f"検索結果（要約なし）:\n{sources}"
    except Exception as e:
        return f"Error: Web検索に失敗しました (fallback): {e}"


def _extract_grounding_sources(response) -> List[dict]:
    """Grounding のソース情報を抽出"""
    sources = []

    try:
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            # Vertex AI のリダイレクト URL から実際の URL を取得するのは難しいので、
                            # タイトルとリダイレクト URL をそのまま使用
                            sources.append({
                                'title': chunk.web.title if hasattr(chunk.web, 'title') else 'Unknown',
                                'url': chunk.web.uri if hasattr(chunk.web, 'uri') else ''
                            })
    except Exception:
        pass  # メタデータ取得に失敗しても回答は返す

    return sources


def webfetch(url: str, question: Optional[str] = None) -> str:
    """
    指定した URL の内容を Gemini で要約して取得します。

    Args:
        url: 取得する URL
        question: URL の内容に対する質問（省略時は要約）

    Returns:
        URL の内容の要約または質問への回答
    """
    use_gemini = HAS_GENAI and _has_gemini_key()

    if use_gemini:
        api_key = os.getenv("GENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        prompt = question or "この URL の内容を日本語で簡潔に要約してください。"
        full_prompt = f"以下の URL の内容について回答してください。\n\nURL: {url}\n\n質問: {prompt}"

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return f"URL: {url}\n\n{response.text}"
        except Exception as e:
            return f"Error: URL の取得に失敗しました (Gemini): {e}"

    if _is_private_url(url):
        return "Error: Access to private/internal URLs is not allowed"

    prompt = question or "この URL の内容を日本語で簡潔に要約してください。"
    try:
        text, content_type, truncated = _fetch_url(url)
        if "text/html" in content_type.lower():
            text = _strip_html(text)
        if len(text) > MAX_FETCH_CHARS:
            text = text[:MAX_FETCH_CHARS] + "... [TRUNCATED]"
        elif truncated:
            text = text + "... [TRUNCATED]"

        provider = get_preferred_provider()
        model = get_analyzer_model(provider)
        full_prompt = f"""以下のURL内容から質問に回答してください。
URL: {url}
質問: {prompt}

本文（抜粋）:
{text}
"""
        try:
            answer = generate_text(prompt=full_prompt, provider=provider, model=model, temperature=0.2, max_tokens=800)
            return f"URL: {url}\n\n{answer}"
        except Exception:
            return f"URL: {url}\n\n本文（抜粋）:\n{text}"
    except Exception as e:
        return f"Error: URL の取得に失敗しました (fallback): {e}"
