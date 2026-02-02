#!/usr/bin/env python3
"""
Grok Search Tool - Web Search and Information Retrieval using xAI Grok API

This tool provides web search capabilities using the Grok API (xAI).
Grok has built-in web search capability that activates automatically.

Usage:
    python grok_search.py "search query"
    python grok_search.py --query "search query" --mode search
    python grok_search.py --query "question" --mode ask
    python grok_search.py --url "https://example.com" --mode summarize
"""

import os
import sys
import json
import argparse
from typing import Optional, Dict, Any

# Try to import requests, fallback to urllib if not available
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# API Configuration
GROK_API_KEY = os.environ.get("GROK_API_KEY")
GROK_API_BASE = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-3-beta"


class GrokSearchClient:
    """Client for Grok API search and chat capabilities."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        """
        Initialize the Grok client.
        
        Args:
            api_key: Grok API key. If not provided, uses GROK_API_KEY env var.
            model: Model name to use (default: grok-3-beta)
        """
        self.api_key = api_key or GROK_API_KEY
        self.model = model
        if not self.api_key:
            raise ValueError(
                "Grok API key is required. Set GROK_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the Grok API."""
        url = f"{GROK_API_BASE}/{endpoint}"
        
        if HAS_REQUESTS:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=self.headers,
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))
    
    def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search the web using Grok."""
        system_prompt = (
            "You are a helpful research assistant. When given a search query, "
            "use your web search capability to find current, accurate information. "
            "Provide a comprehensive answer with specific details, facts, and cite sources. "
            "Structure your response clearly with headings and bullet points."
        )
        
        user_prompt = (
            f"Search the web for current information about: {query}\n\n"
            f"Provide up to {max_results} key findings or results with sources. "
            "Include specific facts, dates, and relevant details."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.7
        }
        
        try:
            response = self._make_request("chat/completions", data)
            return self._parse_response(response, query)
        except Exception as e:
            return {"success": False, "error": str(e), "query": query}
    
    def ask(self, question: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Ask a question and get an answer from Grok."""
        system_prompt = (
            "You are a helpful AI assistant. Answer questions accurately and concisely. "
            "Use web search when the question involves current events or recent data. "
            "Provide clear reasoning and cite sources."
        )
        
        user_content = f"Context: {context}\n\nQuestion: {question}" if context else question
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.7
        }
        
        try:
            response = self._make_request("chat/completions", data)
            return self._parse_response(response, question)
        except Exception as e:
            return {"success": False, "error": str(e), "query": question}
    
    def summarize_url(self, url: str, question: Optional[str] = None) -> Dict[str, Any]:
        """Fetch and summarize content from a URL."""
        system_prompt = (
            "You are a helpful assistant that fetches and summarizes web content. "
            "Access the URL, extract key information, and provide a clear summary."
        )
        
        if question:
            user_prompt = f"Fetch content from {url} and answer: {question}"
        else:
            user_prompt = f"Fetch and summarize the content from: {url}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.5
        }
        
        try:
            response = self._make_request("chat/completions", data)
            return self._parse_response(response, url)
        except Exception as e:
            return {"success": False, "error": str(e), "query": url}
    
    def research(self, topic: str, depth: str = "comprehensive") -> Dict[str, Any]:
        """Deep research on a topic."""
        depth_prompts = {
            "quick": "Provide a brief overview with key facts and current status.",
            "comprehensive": (
                "Provide a detailed analysis including: (1) Overview, (2) Current state, "
                "(3) Key players, (4) Recent developments, (5) Future outlook, (6) Sources."
            ),
            "deep": (
                "Conduct thorough research covering: history, current landscape, "
                "technical details, market analysis, key stakeholders, trends, challenges."
            )
        }
        
        system_prompt = (
            "You are an expert research analyst. Use web search to gather current, "
            "accurate information. Provide well-structured, detailed findings with sources."
        )
        
        user_prompt = f"Research topic: {topic}\n\n{depth_prompts.get(depth, depth_prompts['comprehensive'])}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        try:
            response = self._make_request("chat/completions", data)
            return self._parse_response(response, topic)
        except Exception as e:
            return {"success": False, "error": str(e), "query": topic}
    
    def _parse_response(self, response: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Parse the API response into a structured format."""
        try:
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            
            return {
                "success": True,
                "query": query,
                "answer": content,
                "model": response.get("model"),
                "usage": response.get("usage"),
                "finish_reason": choice.get("finish_reason"),
                "raw_response": response
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse response: {e}",
                "raw_response": response
            }


def format_output(result: Dict[str, Any], format_type: str = "text") -> str:
    """Format the result for display."""
    if format_type == "json":
        clean_result = {k: v for k, v in result.items() if k != "raw_response"}
        return json.dumps(clean_result, indent=2, ensure_ascii=False)
    
    if not result.get("success"):
        return f"Error: {result.get('error', 'Unknown error')}"
    
    output = []
    output.append(f"Query: {result.get('query', 'N/A')}")
    output.append("=" * 60)
    output.append("")
    output.append(result.get("answer", 'No answer provided'))
    output.append("")
    
    if result.get("usage"):
        usage = result["usage"]
        output.append("-" * 60)
        output.append(
            f"Tokens - Prompt: {usage.get('prompt_tokens', 0)}, "
            f"Completion: {usage.get('completion_tokens', 0)}, "
            f"Total: {usage.get('total_tokens', 0)}"
        )
    
    if result.get("model"):
        output.append(f"Model: {result.get('model')}")
    
    return "\n".join(output)


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Grok Search Tool - Web search using xAI Grok API"
    )
    parser.add_argument("query", nargs="?", help="Search query, question, or topic")
    parser.add_argument(
        "--mode", choices=["search", "ask", "summarize", "research"],
        default="search", help="Operation mode (default: search)"
    )
    parser.add_argument("--url", help="URL to summarize (for summarize mode)")
    parser.add_argument("--max-results", type=int, default=5, help="Max search results")
    parser.add_argument(
        "--depth", choices=["quick", "comprehensive", "deep"],
        default="comprehensive", help="Research depth"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--api-key", help="Grok API key")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    
    args = parser.parse_args()
    
    if args.mode == "summarize" and not args.url:
        parser.error("--url is required for summarize mode")
    
    if not args.query and args.mode != "summarize":
        parser.error("query is required")
    
    try:
        client = GrokSearchClient(api_key=args.api_key, model=args.model)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.mode == "search":
        result = client.search(args.query, max_results=args.max_results)
    elif args.mode == "ask":
        result = client.ask(args.query)
    elif args.mode == "summarize":
        result = client.summarize_url(args.url, args.query)
    elif args.mode == "research":
        result = client.research(args.query, depth=args.depth)
    
    print(format_output(result, args.format))
    
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
