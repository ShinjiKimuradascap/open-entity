#!/usr/bin/env python3
"""
Image Encoder Script
Encodes images in a directory to Base64 format
"""

import json
import sys
import base64
from pathlib import Path


# Default supported image extensions
DEFAULT_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff']


def encode_directory(directory_path: str, extensions: list[str] = None) -> dict:
    """
    Encode all images in a directory to Base64 format
    
    Args:
        directory_path: Path to the directory containing images
        extensions: List of image file extensions to process (default: PNG, JPG, JPEG, GIF, WebP, BMP, TIFF)
    
    Returns:
        dict with:
            - status: 'success', 'error', or 'no_images'
            - directory: Processed directory path
            - images_count: Number of images encoded
            - images: List of encoded images with details (filename, extension, size_bytes, base64)
            - error: Error message (if any)
    """
    # Use default extensions if not specified
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS
    
    # Normalize extensions to lowercase and remove leading dots
    extensions = [ext.lower().lstrip('.') for ext in extensions]
    
    # Check if path exists
    directory = Path(directory_path)
    if not directory.exists():
        return {
            'status': 'error',
            'directory': directory_path,
            'images_count': 0,
            'images': [],
            'error': f'Directory not found: {directory_path}'
        }
    
    # Check if path is a directory
    if not directory.is_dir():
        return {
            'status': 'error',
            'directory': directory_path,
            'images_count': 0,
            'images': [],
            'error': f'Path is not a directory: {directory_path}'
        }
    
    # Iterate through files and encode matching images
    images = []
    for file_path in directory.iterdir():
        if file_path.is_file() and file_path.suffix.lower().lstrip('.') in extensions:
            try:
                with open(file_path, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    images.append({
                        'filename': file_path.name,
                        'extension': file_path.suffix.lower().lstrip('.'),
                        'size_bytes': file_path.stat().st_size,
                        'base64': encoded
                    })
            except Exception as e:
                # Skip individual files with encoding errors
                continue
    
    # Check if any images were found
    if not images:
        return {
            'status': 'no_images',
            'directory': directory_path,
            'images_count': 0,
            'images': [],
            'error': f'No images found with extensions: {", ".join(extensions)}'
        }
    
    return {
        'status': 'success',
        'directory': directory_path,
        'images_count': len(images),
        'images': images,
        'error': None
    }


def main():
    """Main entry point for command line execution"""
    if len(sys.argv) < 2:
        print("Usage: python encode_images.py <directory_path> [extensions...]")
        print("\nEncodes all images in a directory to Base64 format")
        print("\nArguments:")
        print("  directory_path  Path to the directory containing images")
        print("  extensions       Optional list of image extensions to process")
        print("                   (default: png, jpg, jpeg, gif, webp, bmp, tiff)")
        print("\nReturns JSON with:")
        print("  - status: 'success', 'error', or 'no_images'")
        print("  - directory: Processed directory path")
        print("  - images_count: Number of images encoded")
        print("  - images: List of encoded images with:")
        print("    - filename: Original filename")
        print("    - extension: File extension (without dot)")
        print("    - size_bytes: File size in bytes")
        print("    - base64: Base64-encoded image data")
        print("  - error: Error message (if any)")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    # Parse optional extensions
    extensions = None
    if len(sys.argv) > 2:
        extensions = sys.argv[2:]
    
    result = encode_directory(directory_path, extensions)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
