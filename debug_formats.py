#!/usr/bin/env python3
import requests
import json

# Test the current behavior
session = requests.Session()

# Upload cookies first
print("Uploading cookies...")
with open('www.youtube.com_cookies (20).txt', 'rb') as f:
    files = {'cookies': f}
    response = session.post('http://localhost:5000/upload_cookies', files=files)
    print(f"Upload status: {response.status_code}")
    if response.status_code == 200:
        print(f"Upload response: {response.json()}")

# Test download with debug
print("\nTesting download...")
data = {'url': 'https://www.youtube.com/shorts/dQw4w9WgXcQ'}
response = session.post('http://localhost:5000/download', json=data, stream=True)
print(f"Download status: {response.status_code}")
print(f"Content-Type: {response.headers.get('Content-Type')}")
print(f"Content-Length: {response.headers.get('Content-Length')}")

# Check if we're getting actual video data or just a small file
if response.status_code == 200:
    content = response.content
    print(f"Actual content size: {len(content)} bytes")
    
    # Check if it's a video file by looking at the first few bytes
    if len(content) > 0:
        print(f"First 20 bytes (hex): {content[:20].hex()}")
        print(f"First 20 bytes (ascii): {content[:20]}")
        
        # Common video file signatures
        if content.startswith(b'\x00\x00\x00\x18ftypmp4') or content.startswith(b'\x00\x00\x00\x20ftypmp4'):
            print("✓ Detected MP4 video file")
        elif content.startswith(b'\x1a\x45\xdf\xa3'):
            print("✓ Detected WebM/MKV video file")
        elif content.startswith(b'FLV'):
            print("✓ Detected FLV video file")
        else:
            print("⚠ Unknown file format - might be thumbnail or corrupted")