#!/usr/bin/env python3
"""
Test script for TikTok and Instagram download functionality
"""

import os
import sys
from pathlib import Path
from yt_dlp import YoutubeDL

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app import build_ydl_opts, get_video_info_and_url, detect_platform

def test_platform_detection():
    """Test platform detection for various URLs"""
    print("=== Testing Platform Detection ===")
    
    test_urls = [
        "https://www.tiktok.com/@username/video/1234567890",
        "https://vm.tiktok.com/ZMabcdef/",
        "https://www.instagram.com/p/ABC123/",
        "https://www.instagram.com/reel/XYZ789/",
        "https://instagram.com/stories/username/123456789/"
    ]
    
    for url in test_urls:
        platform = detect_platform(url)
        print(f"URL: {url}")
        print(f"Detected Platform: {platform}")
        print()

def test_format_options():
    """Test current format selection for TikTok and Instagram"""
    print("=== Testing Format Options ===")
    
    platforms = ['tiktok', 'instagram']
    
    for platform in platforms:
        print(f"\n--- {platform.upper()} Format Options ---")
        opts = build_ydl_opts(platform=platform)
        
        print(f"Format string: {opts.get('format', 'default')}")
        print(f"User Agent: {opts.get('http_headers', {}).get('User-Agent', 'default')}")
        print(f"Socket timeout: {opts.get('socket_timeout', 'default')}")
        print(f"Retries: {opts.get('retries', 'default')}")
        print(f"Merge output format: {opts.get('merge_output_format', 'not set')}")
        print()

def test_real_urls():
    """Test with real URLs (if provided)"""
    print("=== Testing Real URLs ===")
    print("Note: Provide real TikTok/Instagram URLs as command line arguments to test")
    
    if len(sys.argv) > 1:
        for url in sys.argv[1:]:
            platform = detect_platform(url)
            print(f"\nTesting URL: {url}")
            print(f"Platform: {platform}")
            
            if platform in ['tiktok', 'instagram']:
                try:
                    # Test info extraction
                    print("Extracting video info...")
                    result = get_video_info_and_url(url, platform)
                    
                    print(f"Title: {result.get('title', 'N/A')}")
                    print(f"Duration: {result.get('duration', 'N/A')} seconds")
                    print(f"URL available: {'Yes' if result.get('url') else 'No'}")
                    if result.get('url'):
                        print(f"URL (truncated): {result['url'][:100]}...")
                    print(f"Format ID: {result.get('format_id', 'N/A')}")
                    print(f"Extension: {result.get('ext', 'N/A')}")
                    
                except Exception as e:
                    print(f"Error: {str(e)}")
            else:
                print(f"Unsupported platform: {platform}")
    else:
        print("No URLs provided. Usage: python test_tiktok_instagram.py <url1> <url2> ...")

def analyze_yt_dlp_extractors():
    """Analyze available extractors for TikTok and Instagram"""
    print("=== Analyzing yt-dlp Extractors ===")
    
    # Test basic extractor info
    try:
        from yt_dlp.extractor import list_extractors
        extractors = [ie.IE_NAME for ie in list_extractors()]
        
        tiktok_extractors = [e for e in extractors if 'tiktok' in e.lower()]
        instagram_extractors = [e for e in extractors if 'instagram' in e.lower()]
        
        print(f"TikTok extractors: {tiktok_extractors}")
        print(f"Instagram extractors: {instagram_extractors}")
    except Exception as e:
        print(f"Could not analyze extractors: {e}")
    print()

if __name__ == "__main__":
    print("TikTok and Instagram Download Analysis")
    print("=" * 50)
    
    test_platform_detection()
    test_format_options()
    analyze_yt_dlp_extractors()
    test_real_urls()
    
    print("\n=== Analysis Complete ===")
    print("\nKey Findings:")
    print("1. Current format selection is basic for TikTok/Instagram")
    print("2. No platform-specific extraction strategies like YouTube")
    print("3. No specialized user agents or extractor arguments")
    print("4. Missing quality prioritization and format optimization")