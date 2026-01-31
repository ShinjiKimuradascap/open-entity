#!/usr/bin/env python3
"""
Image Encoder Skill - Main Script

This module provides functions to encode image files to Base64 format.
Supports PNG, JPEG/JPG, GIF, WebP, and BMP formats.
"""

import base64
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


# Supported image extensions
SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

# MIME type mapping
MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp'
}


def _get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension."""
    ext = Path(file_path).suffix.lower()
    return MIME_TYPES.get(ext, 'application/octet-stream')


def _is_supported_image(file_path: str) -> bool:
    """Check if file has a supported image extension."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def _get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(file_path)


def _resolve_path(path: str) -> str:
    """Resolve path to absolute path."""
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = Path.cwd() / path_obj
    return str(path_obj.resolve())


def encode_image(image_path: str, include_metadata: bool = False) -> str:
    """
    Encodes a single image file to Base64 format.
    
    Args:
        image_path: Path to the image file to encode
        include_metadata: Returns metadata along with Base64 string
        
    Returns:
        JSON string containing the Base64 encoded data and optional metadata
        
    Example with include_metadata=false:
        {"base64": "iVBORw0KGgoAAAANSUhEUgAA..."}
        
    Example with include_metadata=true:
        {"base64": "iVBORw0KGgoAAAANSUhEUgAA...", "filename": "screenshot.png", "mime_type": "image/png", "file_size": 45678}
    """
    result = {}
    errors = []
    
    try:
        # Resolve path
        resolved_path = _resolve_path(image_path)
        
        # Check if file exists
        if not os.path.isfile(resolved_path):
            errors.append(f"File not found: {image_path}")
            result['error'] = errors
            return json.dumps(result, ensure_ascii=False)
        
        # Check if file is supported
        if not _is_supported_image(resolved_path):
            errors.append(f"Unsupported file type: {Path(resolved_path).suffix}")
            result['error'] = errors
            return json.dumps(result, ensure_ascii=False)
        
        # Read and encode file
        with open(resolved_path, 'rb') as f:
            file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            result['base64'] = base64_data
        
        # Add metadata if requested
        if include_metadata:
            result['filename'] = os.path.basename(resolved_path)
            result['mime_type'] = _get_mime_type(resolved_path)
            result['file_size'] = _get_file_size(resolved_path)
        
    except Exception as e:
        errors.append(f"Error encoding image: {str(e)}")
        result['error'] = errors
    
    return json.dumps(result, ensure_ascii=False)


def encode_directory(
    directory_path: str,
    recursive: bool = False,
    include_metadata: bool = False,
    max_file_size_mb: float = 10.0
) -> str:
    """
    Encodes all supported image files in a directory to Base64 format.
    
    Args:
        directory_path: Path to the directory containing images
        recursive: Searches subdirectories recursively
        include_metadata: Returns metadata for each image
        max_file_size_mb: Maximum file size in MB to encode
        
    Returns:
        JSON string containing encoded images and processing information
        
    Example with include_metadata=false:
        {"logo.png": "iVBORw0KGgoAAAANSUhEUgAA...", "banner.jpg": "/9j/4AAQSkZJRgABAQAAAQABAAD...", "total_count": 2}
        
    Example with include_metadata=true:
        {"logo.png": {"base64": "iVBORw0KGgoAAAANSUhEUgAA...", "mime_type": "image/png", "file_size": 12345, "relative_path": "logo.png"}, "total_count": 1, "skipped": [], "errors": []}
    """
    result = {}
    skipped = []
    errors = []
    total_count = 0
    
    try:
        # Resolve path
        resolved_path = _resolve_path(directory_path)
        
        # Check if directory exists
        if not os.path.isdir(resolved_path):
            errors.append(f"Directory not found: {directory_path}")
            result['error'] = errors
            result['total_count'] = 0
            result['skipped'] = skipped
            return json.dumps(result, ensure_ascii=False)
        
        # Determine which files to process
        if recursive:
            # Walk through directory tree
            for root, dirs, files in os.walk(resolved_path):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    if _is_supported_image(file_path):
                        _process_file(file_path, resolved_path, include_metadata, max_file_size_mb, result, skipped, errors)
                        total_count += 1
        else:
            # Only process files in top-level directory
            for item in os.listdir(resolved_path):
                file_path = os.path.join(resolved_path, item)
                if os.path.isfile(file_path) and _is_supported_image(file_path):
                    _process_file(file_path, resolved_path, include_metadata, max_file_size_mb, result, skipped, errors)
                    total_count += 1
        
        # Add summary information
        result['total_count'] = total_count
        
        if include_metadata:
            result['skipped'] = skipped
            result['errors'] = errors
        
    except Exception as e:
        errors.append(f"Error processing directory: {str(e)}")
        result['error'] = errors
        result['total_count'] = total_count
        result['skipped'] = skipped
    
    return json.dumps(result, ensure_ascii=False)


def _process_file(
    file_path: str,
    base_path: str,
    include_metadata: bool,
    max_file_size_mb: float,
    result: Dict[str, Any],
    skipped: List[str],
    errors: List[str]
) -> None:
    """
    Process a single file for encoding.
    
    Args:
        file_path: Full path to the file
        base_path: Base directory path for calculating relative paths
        include_metadata: Whether to include metadata
        max_file_size_mb: Maximum file size in MB
        result: Result dictionary to populate
        skipped: List of skipped files
        errors: List of errors
    """
    try:
        file_size = _get_file_size(file_path)
        max_size_bytes = max_file_size_mb * 1024 * 1024
        
        # Check file size
        if file_size > max_size_bytes:
            rel_path = os.path.relpath(file_path, base_path)
            skipped.append({
                'file': rel_path,
                'reason': f'File size ({file_size} bytes) exceeds maximum ({max_size_bytes} bytes)'
            })
            return
        
        # Encode file
        with open(file_path, 'rb') as f:
            file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
        
        # Calculate relative path for key
        rel_path = os.path.relpath(file_path, base_path)
        
        # Add to result
        if include_metadata:
            result[rel_path] = {
                'base64': base64_data,
                'mime_type': _get_mime_type(file_path),
                'file_size': file_size,
                'relative_path': rel_path
            }
        else:
            result[rel_path] = base64_data
            
    except Exception as e:
        rel_path = os.path.relpath(file_path, base_path)
        errors.append({
            'file': rel_path,
            'error': str(e)
        })


def list_images(directory_path: str, recursive: bool = False) -> str:
    """
    Lists all image files in a directory without encoding them.
    
    Args:
        directory_path: Path to the directory to scan for images
        recursive: Searches subdirectories recursively
        
    Returns:
        JSON string containing list of image files and summary
        
    Example:
        {"images": [{"filename": "logo.png", "relative_path": "assets/logo.png", "file_size": 12345, "mime_type": "image/png"}], "total_count": 1, "total_size_bytes": 12345}
    """
    result = {
        'images': [],
        'total_count': 0,
        'total_size_bytes': 0
    }
    errors = []
    
    try:
        # Resolve path
        resolved_path = _resolve_path(directory_path)
        
        # Check if directory exists
        if not os.path.isdir(resolved_path):
            errors.append(f"Directory not found: {directory_path}")
            result['error'] = errors
            return json.dumps(result, ensure_ascii=False)
        
        # Scan for images
        images = []
        total_size = 0
        
        if recursive:
            # Walk through directory tree
            for root, dirs, files in os.walk(resolved_path):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    if _is_supported_image(file_path):
                        file_size = _get_file_size(file_path)
                        rel_path = os.path.relpath(file_path, resolved_path)
                        
                        images.append({
                            'filename': filename,
                            'relative_path': rel_path,
                            'file_size': file_size,
                            'mime_type': _get_mime_type(file_path)
                        })
                        total_size += file_size
        else:
            # Only scan top-level directory
            for item in os.listdir(resolved_path):
                file_path = os.path.join(resolved_path, item)
                if os.path.isfile(file_path) and _is_supported_image(file_path):
                    file_size = _get_file_size(file_path)
                    rel_path = os.path.relpath(file_path, resolved_path)
                    
                    images.append({
                        'filename': item,
                        'relative_path': rel_path,
                        'file_size': file_size,
                        'mime_type': _get_mime_type(file_path)
                    })
                    total_size += file_size
        
        # Sort images by relative path for consistent output
        images.sort(key=lambda x: x['relative_path'])
        
        # Update result
        result['images'] = images
        result['total_count'] = len(images)
        result['total_size_bytes'] = total_size
        
    except Exception as e:
        errors.append(f"Error listing images: {str(e)}")
        result['error'] = errors
    
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    # For testing purposes
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <command> [args...]")
        print("Commands: encode_image, encode_directory, list_images")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "encode_image":
        if len(sys.argv) < 3:
            print("Usage: python main.py encode_image <image_path> [--metadata]")
            sys.exit(1)
        
        image_path = sys.argv[2]
        include_metadata = "--metadata" in sys.argv
        print(encode_image(image_path, include_metadata))
    
    elif command == "encode_directory":
        if len(sys.argv) < 3:
            print("Usage: python main.py encode_directory <directory_path> [--recursive] [--metadata] [--max-size <mb>]")
            sys.exit(1)
        
        directory_path = sys.argv[2]
        recursive = "--recursive" in sys.argv
        include_metadata = "--metadata" in sys.argv
        
        max_file_size_mb = 10.0
        if "--max-size" in sys.argv:
            idx = sys.argv.index("--max-size")
            if idx + 1 < len(sys.argv):
                max_file_size_mb = float(sys.argv[idx + 1])
        
        print(encode_directory(directory_path, recursive, include_metadata, max_file_size_mb))
    
    elif command == "list_images":
        if len(sys.argv) < 3:
            print("Usage: python main.py list_images <directory_path> [--recursive]")
            sys.exit(1)
        
        directory_path = sys.argv[2]
        recursive = "--recursive" in sys.argv
        print(list_images(directory_path, recursive))
    
    else:
        print(f"Unknown command: {command}")
        print("Commands: encode_image, encode_directory, list_images")
        sys.exit(1)
