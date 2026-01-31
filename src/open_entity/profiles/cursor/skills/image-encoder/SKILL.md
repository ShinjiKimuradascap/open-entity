---
name: image-encoder
description: Encode image files in a directory to Base64 format
tools:
  - name: encode_directory
    description: Encode all image files in the specified directory to Base64 format
    parameters:
      directory_path:
        type: string
        description: Path to the directory containing images
      extensions:
        type: array
        items:
          type: string
        description: List of image file extensions
        default: [png, jpg, jpeg, gif, webp, bmp, tiff]
    returns:
      type: object
      properties:
        status: {type: string, description: success or error}
        directory: {type: string, description: Directory path}
        images_count: {type: number, description: Number of encoded images}
        images: {type: array, items: {type: object, properties: {filename: string, extension: string, size_bytes: number, base64: string}}}
        error: {type: string, description: Error message}
---

# Image Encoder

## Overview

The image-encoder skill encodes image files to Base64 format.

## Supported Formats

PNG, JPG, JPEG, GIF, WebP, BMP, TIFF

## Tool Usage

### encode_directory

Encodes all image files in a directory.

Parameters:
- directory_path (string, required): Path to the directory
- extensions (array, optional): File extensions to process

Returns JSON with status, directory, images_count, images array, and error field.

## Error Handling

Returns error status if:
- Directory not found
- Not a directory
- No images found
- Encoding errors (file is skipped)

## Implementation Guidelines

Use os.path.exists(), os.path.isdir(), os.listdir(), base64.b64encode().

Example:

import os
import base64

def encode_directory(directory_path: str, extensions: list = None) -> dict:
    if extensions is None:
        extensions = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff']
    
    if not os.path.exists(directory_path):
        return {'status': 'error', 'error': f'Directory not found: {directory_path}', 'directory': directory_path, 'images_count': 0, 'images': []}
    
    if not os.path.isdir(directory_path):
        return {'status': 'error', 'error': f'Not a directory: {directory_path}', 'directory': directory_path, 'images_count': 0, 'images': []}
    
    images = []
    for entry in os.listdir(directory_path):
        full_path = os.path.join(directory_path, entry)
        if os.path.isfile(full_path):
            _, ext = os.path.splitext(entry)
            if ext.lower().lstrip('.') in [e.lower() for e in extensions]:
                try:
                    with open(full_path, 'rb') as f:
                        encoded = base64.b64encode(f.read()).decode('utf-8')
                        images.append({
                            'filename': entry,
                            'extension': ext.lstrip('.'),
                            'size_bytes': os.path.getsize(full_path),
                            'base64': encoded
                        })
                except Exception:
                    pass
    
    if not images:
        return {'status': 'error', 'error': 'No image files found', 'directory': directory_path, 'images_count': 0, 'images': []}
    
    return {'status': 'success', 'directory': directory_path, 'images_count': len(images), 'images': images, 'error': None}
