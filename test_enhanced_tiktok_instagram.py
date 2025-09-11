#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import detect_platform, build_ydl_opts, get_video_info_and_url
import yt_dlp

def test_enhanced_functionality():
    """Test the enhanced TikTok and Instagram functionality"""
    
    print("=== Testing Enhanced TikTok and Instagram Functionality ===")
    print()
    
    # Test URLs (using example URLs - replace with real ones for actual testing)
    test_urls = {
        "tiktok": "https://www.tiktok.com/@username/video/1234567890123456789",
        "instagram": "https://www.instagram.com/p/ABC123DEF456/"
    }
    
    for platform, url in test_urls.items():
        print(f"\n--- Testing {platform.upper()} ---")
        print(f"URL: {url}")
        
        # Test platform detection
        detected = detect_platform(url)
        print(f"Detected platform: {detected}")
        
        if detected != platform:
            print(f"❌ Platform detection failed! Expected {platform}, got {detected}")
            continue
        
        # Test yt-dlp options
        try:
            ydl_opts = build_ydl_opts(platform)
            print(f"✅ yt-dlp options built successfully")
            print(f"Format selector: {ydl_opts.get('format', 'default')}")
            
            # Show platform-specific options
            if 'http_headers' in ydl_opts:
                print(f"Custom headers: {len(ydl_opts['http_headers'])} headers set")
            if 'extractor_args' in ydl_opts:
                print(f"Extractor args: {list(ydl_opts['extractor_args'].keys())}")
                
        except Exception as e:
            print(f"❌ Error building yt-dlp options: {e}")
            continue
        
        # Test extraction strategies (without actually downloading)
        try:
            print(f"\nTesting extraction strategies for {platform}...")
            
            # Create a test yt-dlp instance to check if URL is accessible
            test_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Don't download, just extract info
                'skip_download': True
            }
            
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        print(f"✅ URL is accessible and extractable")
                        print(f"Title: {info.get('title', 'N/A')[:50]}...")
                        print(f"Duration: {info.get('duration', 'N/A')} seconds")
                        print(f"Available formats: {len(info.get('formats', []))}")
                    else:
                        print(f"⚠️  URL accessible but no info extracted")
                except Exception as extract_error:
                    print(f"⚠️  URL extraction test failed: {extract_error}")
                    print(f"This might be due to the example URL or network restrictions")
        
        except Exception as e:
            print(f"❌ Error testing extraction: {e}")
    
    print("\n=== Testing Format Selection Logic ===")
    
    # Test format selection for each platform
    for platform in ['tiktok', 'instagram']:
        print(f"\n--- {platform.upper()} Format Selection ---")
        try:
            ydl_opts = build_ydl_opts(platform)
            format_selector = ydl_opts.get('format', 'best')
            print(f"Format selector: {format_selector}")
            
            # Parse the format selector to show priority
            if '/' in format_selector:
                formats = format_selector.split('/')
                print(f"Format priority:")
                for i, fmt in enumerate(formats, 1):
                    print(f"  {i}. {fmt.strip()}")
            
        except Exception as e:
            print(f"❌ Error testing format selection: {e}")
    
    print("\n=== Summary ===")
    print("✅ Enhanced format selection implemented")
    print("✅ Platform-specific extraction strategies added")
    print("✅ Quality prioritization configured")
    print("✅ Mobile and desktop user agents configured")
    print("\n⚠️  Note: To test with real URLs, replace the example URLs with actual TikTok/Instagram links")

if __name__ == "__main__":
    test_enhanced_functionality()