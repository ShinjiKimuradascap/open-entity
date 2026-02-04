# -*- coding: utf-8 -*-
"""画像解析ツール（Vision API統一インターフェース）"""
import base64
import ipaddress
import os
import re
import socket
from typing import Optional
from urllib.parse import urlparse

from open_entity.core.llm_provider import (
    PROVIDER_GEMINI,
    generate_vision,
    get_vision_model,
    get_vision_provider,
    resolve_provider_and_model,
)


# 画像の拡張子
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# MIMEタイプマッピング
EXTENSION_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _is_url(source: str) -> bool:
    """URLかどうか判定"""
    return source.startswith(("http://", "https://"))


def _is_private_ip(url: str) -> bool:
    """URLがプライベートIPを指しているか判定（SSRF対策）"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True

        # localhost チェック
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return True

        # IP アドレスの場合
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            # ホスト名の場合は DNS 解決
            try:
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
                return ip.is_private or ip.is_loopback or ip.is_reserved
            except socket.gaierror:
                return False
    except Exception:
        return True  # 判定できない場合は安全側に倒す


def _is_base64(source: str) -> bool:
    """Base64文字列かどうか判定"""
    # data URI scheme
    if source.startswith("data:image/"):
        return True
    # 純粋なBase64（長い文字列で、Base64文字のみ）
    if len(source) > 100:
        base64_pattern = re.compile(r"^[A-Za-z0-9+/=]+$")
        # 最初の1000文字で判定（パフォーマンス考慮）
        return bool(base64_pattern.match(source[:1000]))
    return False


def _is_file_path(source: str) -> bool:
    """ファイルパスかどうか判定"""
    return os.path.isfile(source)


def _get_mime_type_from_path(file_path: str) -> str:
    """ファイルパスからMIMEタイプを取得"""
    ext = os.path.splitext(file_path)[1].lower()
    return EXTENSION_TO_MIME.get(ext, "image/png")


def _load_image_as_base64(file_path: str) -> tuple[str, str]:
    """ファイルを読み込んでBase64とMIMEタイプを返す"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")

    mime_type = _get_mime_type_from_path(file_path)

    with open(file_path, "rb") as f:
        image_data = f.read()

    return base64.b64encode(image_data).decode("utf-8"), mime_type


def _parse_base64_source(source: str) -> tuple[str, str]:
    """Base64ソースをパースしてデータとMIMEタイプを返す"""
    # data URI scheme: data:image/png;base64,xxxxx
    if source.startswith("data:"):
        match = re.match(r"data:(image/[^;]+);base64,(.+)", source)
        if match:
            return match.group(2), match.group(1)
    # 純粋なBase64
    return source, "image/png"  # デフォルトはPNG


def _download_image_as_base64(image_url: str) -> tuple[str, str]:
    """URL画像をダウンロードして base64 と MIME を返す（SSRF対策込み）。"""
    if _is_private_ip(image_url):
        raise ValueError("Access to private/internal URLs is not allowed")
    try:
        import urllib.request
        with urllib.request.urlopen(image_url, timeout=30) as response:
            image_data = response.read()
        base64_data = base64.b64encode(image_data).decode("utf-8")
        parsed = urlparse(image_url)
        ext = os.path.splitext(parsed.path)[1].lower()
        mime_type = EXTENSION_TO_MIME.get(ext, "image/png")
        return base64_data, mime_type
    except Exception as e:
        raise RuntimeError(f"Error downloading image from URL: {e}")


def analyze_image(
    image_source: str,
    question: str = "この画像を詳しく説明してください",
    provider: Optional[str] = None,
) -> str:
    """
    画像を解析し、質問に対する回答を返す。

    対応プロバイダ:
    - gemini: Gemini Vision API (gemini-2.0-flash)
    - openai: OpenAI Vision API (gpt-4o)
    - openrouter: OpenRouter経由のVision API

    Args:
        image_source: 画像のパス、URL、またはBase64文字列
        question: 画像に対する質問
        provider: 使用するプロバイダ（gemini/openai/openrouter）
                  Noneの場合は環境変数から自動選択

    Returns:
        str: 画像の分析結果

    Examples:
        # ファイルパスから
        analyze_image("screenshot.png", "この画面の内容を説明してください")

        # URLから
        analyze_image("https://example.com/image.jpg", "何が写っていますか？")

        # Base64から
        analyze_image("data:image/png;base64,iVBOR...", "この図の意味は？")

        # プロバイダ指定
        analyze_image("image.png", provider="openai")
    """
    # 入力バリデーション
    if not image_source:
        return "Error: image_source is required"

    if not question:
        question = "この画像を詳しく説明してください"

    # プロバイダ・モデルの決定
    model_override: Optional[str] = None
    if provider:
        provider_name, model_override = resolve_provider_and_model(provider, None)
    else:
        provider_name = get_vision_provider()

    if provider_name not in ("gemini", "openai", "openrouter", "moonshot"):
        return f"Error: Unsupported provider: {provider_name}. Use gemini, openai, openrouter, or moonshot"

    # 画像ソースの処理
    base64_data: Optional[str] = None
    mime_type = "image/png"

    image_url: Optional[str] = None

    if _is_url(image_source):
        # URLはそのまま（OpenAI系）またはダウンロード（Gemini）
        if provider_name == PROVIDER_GEMINI:
            try:
                base64_data, mime_type = _download_image_as_base64(image_source)
            except Exception as e:
                return str(e)
        else:
            if _is_private_ip(image_source):
                return "Error: Access to private/internal URLs is not allowed"
            image_url = image_source
    elif _is_base64(image_source):
        # Base64文字列
        base64_data, mime_type = _parse_base64_source(image_source)
    elif _is_file_path(image_source):
        # ファイルパス
        try:
            base64_data, mime_type = _load_image_as_base64(image_source)
        except FileNotFoundError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading image file: {e}"
    else:
        return f"Error: Invalid image source. Not a valid URL, file path, or Base64 string: {image_source[:100]}..."

    model_name = model_override or get_vision_model(provider_name)
    max_tokens = 1024 if provider_name in ("openai", "openrouter", "moonshot") else None

    try:
        return generate_vision(
            prompt=question,
            image_url=image_url,
            image_base64=base64_data,
            image_mime_type=mime_type,
            provider=provider_name,
            model=model_name,
            max_tokens=max_tokens,
        )
    except Exception as e:
        return f"Error: {e}"
