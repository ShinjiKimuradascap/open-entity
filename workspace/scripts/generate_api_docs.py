#!/usr/bin/env python3
"""
API Documentation Generator

Generates OpenAPI schema and Markdown documentation from FastAPI app.
Usage: python scripts/generate_api_docs.py [--format openapi|markdown]
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def generate_openapi_schema():
    """Generate OpenAPI schema from FastAPI app"""
    try:
        from services.api_server import app
        schema = app.openapi()
        return schema
    except Exception as e:
        print(f"Error generating schema: {e}", file=sys.stderr)
        return None

def generate_markdown_docs(schema: dict) -> str:
    """Generate Markdown documentation from OpenAPI schema"""
    lines = []
    
    # Title
    title = schema.get("info", {}).get("title", "API Documentation")
    version = schema.get("info", {}).get("version", "1.0.0")
    description = schema.get("info", {}).get("description", "")
    
    lines.append(f"# {title}")
    lines.append(f"\n**Version**: {version}")
    lines.append(f"\n{description}")
    lines.append("\n---\n")
    
    # Endpoints by path
    paths = schema.get("paths", {})
    
    # Group by tag
    endpoints_by_tag = {}
    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                tags = details.get("tags", ["General"])
                tag = tags[0] if tags else "General"
                
                if tag not in endpoints_by_tag:
                    endpoints_by_tag[tag] = []
                
                endpoints_by_tag[tag].append({
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "description": details.get("description", ""),
                    "parameters": details.get("parameters", []),
                    "request_body": details.get("requestBody"),
                    "responses": details.get("responses", {})
                })
    
    # Output by tag
    for tag, endpoints in sorted(endpoints_by_tag.items()):
        lines.append(f"\n## {tag}\n")
        
        for ep in endpoints:
            lines.append(f"### {ep['method']} {ep['path']}")
            if ep["summary"]:
                lines.append(f"\n**{ep['summary']}**")
            if ep["description"]:
                lines.append(f"\n{ep['description']}")
            
            # Parameters
            if ep["parameters"]:
                lines.append("\n**Parameters**:")
                for param in ep["parameters"]:
                    name = param.get("name", "")
                    param_in = param.get("in", "")
                    required = " (required)" if param.get("required") else ""
                    desc = param.get("description", "")
                    lines.append(f"- `{name}` ({param_in}){required}: {desc}")
            
            # Request body
            if ep["request_body"]:
                lines.append("\n**Request Body**: Required")
            
            lines.append("")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Generate API documentation")
    parser.add_argument("--format", choices=["openapi", "markdown"], default="openapi",
                       help="Output format")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()
    
    schema = generate_openapi_schema()
    if not schema:
        sys.exit(1)
    
    if args.format == "openapi":
        output = json.dumps(schema, indent=2, default=str)
    else:
        output = generate_markdown_docs(schema)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Documentation written to {args.output}")
    else:
        print(output)

if __name__ == "__main__":
    main()
