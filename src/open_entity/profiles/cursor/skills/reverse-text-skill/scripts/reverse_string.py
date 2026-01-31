#!/usr/bin/env python3
"""
Reverse String Tool
Provides a simple function to reverse text strings.
"""

import json
import sys


def reverse_string(text: str) -> str:
    """
    Reverse a given text string.
    
    Args:
        text: The text string to reverse
        
    Returns:
        The reversed text string
    """
    return text[::-1]


def main():
    """
    Main entry point for the tool.
    Reads JSON from stdin and writes result to stdout.
    
    Expected input format:
    {"text": "your text here"}
    
    Output format:
    {"result": "your reversed text here"}
    """
    if len(sys.argv) > 1:
        # Argument passed via command line
        try:
            input_data = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON argument"}))
            sys.exit(1)
    else:
        # Read from stdin
        try:
            input_data = json.loads(sys.stdin.read())
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON input from stdin"}))
            sys.exit(1)
    
    # Validate input
    if "text" not in input_data:
        print(json.dumps({"error": "Missing 'text' parameter"}))
        sys.exit(1)
    
    # Execute reverse_string
    text = input_data["text"]
    result = reverse_string(text)
    
    # Output result
    print(json.dumps({"result": result}))


if __name__ == "__main__":
    main()
