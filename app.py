#!/usr/bin/env python3
"""
VideoCatcher app.py
Full-featured Flask app:
 - Download videos (YouTube/TikTok/Instagram) via yt-dlp
 - Uses cookies.txt automatically if present (for YouTube restricted videos)
 - Admin UI to upload/delete cookies.txt (password controlled)
 - Optional API endpoint for automated cookie sync (token protected)
 - Download history (history.json)
 - Background cleanup of old downloads (configurable)
"""

import os
import uuid
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, send_from_directory, abort, Response
)
import requests
from werkzeug.utils import secure_filename
from yt_dlp import YoutubeDL

# -----------------------------
# Configuration (override via ENV)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", BASE_DIR / "downloads"))
COOKIES_PATH = Path(os.getenv("COOKIES_PATH", BASE_DIR / "cookies/cookies.txt"))
HISTORY_PATH = Path(os.getenv("HISTORY_PATH", BASE_DIR / "history.json"))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")        # change it in production
API_UPLOAD_TOKEN = os.getenv("API_UPLOAD_TOKEN", "")            # set to a secret for automated upload
DOWNLOAD_TTL_MINUTES = int(os.getenv("DOWNLOAD_TTL_MINUTES", "120"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "200"))
COOKIES_VALIDITY_MINUTES = int(os.getenv("COOKIES_VALIDITY_MINUTES", "15"))  # Cookie validity period
FLASK_SECRET = os.getenv("FLASK_SECRET", uuid.uuid4().hex)

# Ensure folders exist
# DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # No longer needed - videos are streamed directly
BASE_DIR.joinpath("cookies").parent.mkdir(exist_ok=True)  # ensure parent exists

# Flask app
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("VideoCatcher")

# -----------------------------
# Utilities: history, cleanup
# -----------------------------
_history_lock = threading.Lock()


def load_history():
    if HISTORY_PATH.exists():
        try:
            with HISTORY_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read history.json: %s", e)
            return []
    return []


def save_history(history_list):
    try:
        # keep last MAX_HISTORY entries
        trimmed = history_list[-MAX_HISTORY:]
        with HISTORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to save history.json: %s", e)


def append_history(entry: dict):
    with _history_lock:
        history = load_history()
        history.append(entry)
        save_history(history)


def save_cookie_timestamp(user_id: str):
    """Save the timestamp when user uploads cookies"""
    try:
        timestamp_file = BASE_DIR / "cookies" / user_id / "upload_timestamp.json"
        timestamp_data = {
            "upload_time": datetime.utcnow().isoformat(),
            "user_id": user_id
        }
        with timestamp_file.open("w", encoding="utf-8") as f:
            json.dump(timestamp_data, f)
        logger.info(f"Saved cookie timestamp for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to save cookie timestamp for user {user_id}: {e}")


def are_cookies_valid(user_id: str) -> bool:
    """Check if user's cookies are still valid (within 10 minutes of upload)"""
    try:
        if not user_id:
            return False
            
        user_cookies_path = BASE_DIR / "cookies" / user_id / "cookies.txt"
        timestamp_file = BASE_DIR / "cookies" / user_id / "upload_timestamp.json"
        
        # Check if cookies file exists
        if not user_cookies_path.exists():
            return False
            
        # Check if timestamp file exists
        if not timestamp_file.exists():
            return False
            
        # Load timestamp data
        with timestamp_file.open("r", encoding="utf-8") as f:
            timestamp_data = json.load(f)
            
        upload_time = datetime.fromisoformat(timestamp_data["upload_time"])
        current_time = datetime.utcnow()
        time_diff = current_time - upload_time
        
        # Check if within validity period
        is_valid = time_diff.total_seconds() <= (COOKIES_VALIDITY_MINUTES * 60)
        
        if not is_valid:
            logger.info(f"Cookies expired for user {user_id}. Uploaded {time_diff.total_seconds()/60:.1f} minutes ago")
        
        return is_valid
        
    except Exception as e:
        logger.warning(f"Failed to check cookie validity for user {user_id}: {e}")
        return False


def cleanup_old_files_loop(folder: Path, ttl_minutes: int):
    ttl = timedelta(minutes=ttl_minutes)
    logger.info("Cleanup thread starting: remove files older than %s minutes", ttl_minutes)
    while True:
        try:
            now = datetime.utcnow()
            for p in folder.iterdir():
                try:
                    if p.is_file():
                        mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
                        if now - mtime > ttl:
                            logger.info("Removing old file: %s", p)
                            p.unlink()
                except Exception as e:
                    logger.debug("Skipping during cleanup %s: %s", p, e)
        except Exception as e:
            logger.exception("Cleanup loop error: %s", e)
        time.sleep(600)  # check every 10 minutes


# _cleanup_thread = threading.Thread(target=cleanup_old_files_loop, args=(DOWNLOADS_DIR, DOWNLOAD_TTL_MINUTES), daemon=True)
# _cleanup_thread.start()  # No longer needed - videos are streamed directly

# -----------------------------
# Helpers: platform detect, ytdl
# -----------------------------
def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u or "instagr.am" in u:
        return "instagram"
    return "unknown"


def build_ydl_opts(output_template: str = None, platform: str = None, user_id: str = None):
    base = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": "/app/.cache",
        "no_check_certificate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }
    
    # Add output template only if provided (for actual downloads)
    if output_template:
        base["outtmpl"] = output_template

    # Add proxy support if configured
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        base["proxy"] = proxy_url
        logger.info("Using proxy: %s", proxy_url)
    
    # Additional options to improve compatibility and quality
    base["socket_timeout"] = 30
    base["retries"] = 3
    base["fragment_retries"] = 3
    base["skip_unavailable_fragments"] = True
    base["keep_fragments"] = False
    base["abort_on_unavailable_fragment"] = False
    # Quality preferences - prioritize higher quality like yt-dlp command line
    base["prefer_free_formats"] = False  # Don't prefer free formats over higher quality
    base["youtube_include_dash_manifest"] = True  # Include DASH formats for better quality
    
    # Platform-specific configurations - prioritize high quality formats
    if platform == "youtube":
        # Enhanced format selection to prioritize higher resolution
        # Try best video+audio combo first, then fallback to best available
        base["format"] = "bestvideo[height>=1080]+bestaudio/bestvideo[height>=720]+bestaudio/bestvideo+bestaudio/best[height>=720]/best"
        # Additional YouTube-specific options for better quality
        base["writesubtitles"] = False
        base["writeautomaticsub"] = False
        base["ignoreerrors"] = False
        # Force merge output format to ensure best quality
        base["merge_output_format"] = "mp4"
    elif platform == "tiktok":
        base["format"] = "bestvideo+bestaudio/best"
    elif platform == "instagram":
        base["format"] = "bestvideo+bestaudio/best"
    else:
        base["format"] = "bestvideo+bestaudio/best"

    # Check for user-specific cookies first, then fall back to global cookies
    cookies_used = False
    if user_id:
        user_cookies_path = BASE_DIR / "cookies" / user_id / "cookies.txt"
        if user_cookies_path.exists():
            base["cookiefile"] = str(user_cookies_path)
            logger.info("Using user cookies file: %s", user_cookies_path)
            cookies_used = True
    
    if not cookies_used and COOKIES_PATH.exists():
        base["cookiefile"] = str(COOKIES_PATH)
        logger.info("Using global cookies file: %s", COOKIES_PATH)
        cookies_used = True
    
    if not cookies_used:
        logger.warning("No cookies file found - some videos may be restricted")

    return base


def get_video_info_and_url(url: str, platform: str, user_id: str = None) -> dict:
    """Extract video information and direct download URL without downloading the file"""
    # Multiple extraction strategies for better success rate
    extraction_strategies = [
        # Strategy 1: Web client (best quality, no restrictions)
        {
            "name": "Web Client",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "web"
                }
            }
        },
        # Strategy 2: iOS client (no skip restrictions)
        {
            "name": "iOS Client",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "extractor_args": {
                "youtube": {
                    "player_client": "ios"
                }
            }
        },
        # Strategy 3: Android client (no skip restrictions)
        {
            "name": "Android Client",
            "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "android"
                }
            }
        },
        # Strategy 4: TV client
        {
            "name": "TV Client",
            "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "tv"
                }
            }
        },
        # Strategy 5: TV Embedded client
        {
            "name": "TV Embedded Client",
            "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "tv_embedded"
                }
            }
        },
        # Strategy 6: Web Music client
        {
            "name": "Web Music Client",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "web_music"
                }
            }
        }
    ]
     
    last_error = None
    
    for attempt, strategy in enumerate(extraction_strategies, 1):
        try:
            opts = build_ydl_opts(None, platform, user_id)  # No output template needed
            opts["noplaylist"] = True
            
            # Apply strategy-specific configurations
            opts["http_headers"]["User-Agent"] = strategy["user_agent"]
            if "extractor_args" in strategy:
                if "extractor_args" not in opts:
                    opts["extractor_args"] = {}
                opts["extractor_args"].update(strategy["extractor_args"])
            
            # Format selection is now handled in build_ydl_opts with enhanced quality prioritization
            # No need to override here as build_ydl_opts already sets optimal format selection
            
            # Add detailed format logging
            opts["listformats"] = False  # Don't list formats, but log selected format
            opts["verbose"] = True  # Enable verbose logging to see format selection
            
            logger.info("Info extraction attempt %d/%d using %s strategy: %s (platform=%s)", 
                       attempt, len(extraction_strategies), strategy["name"], url, platform)
            logger.info("Using format string: %s", opts.get("format", "default"))
            
            with YoutubeDL(opts) as ydl:
                # Extract info without downloading
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise RuntimeError("Failed to extract video info")
                
                # Log detailed format information
                if 'formats' in info and info['formats']:
                    logger.info("Available formats count: %d", len(info['formats']))
                    # Log details of top 10 formats for debugging, including URLs
                    for i, fmt in enumerate(info['formats'][:10]):
                        url = fmt.get('url', 'N/A')
                        url_type = 'M3U8' if url.endswith('.m3u8') else 'MPD' if url.endswith('.mpd') else 'Direct'
                        logger.info("Format %d: ID=%s, Resolution=%sx%s, FPS=%s, VCodec=%s, ACodec=%s, URL_Type=%s", 
                                   i+1, fmt.get('format_id', 'N/A'), 
                                   fmt.get('width', 'N/A'), fmt.get('height', 'N/A'),
                                   fmt.get('fps', 'N/A'), fmt.get('vcodec', 'N/A'), fmt.get('acodec', 'N/A'), url_type)
                
                # Get the best format URL - prioritize direct URLs over HLS/DASH
                video_url = None
                selected_format = None
                
                if 'requested_formats' in info and info['requested_formats']:
                    # yt-dlp selected multiple formats (video+audio), use the video format URL
                    for fmt in info['requested_formats']:
                        if fmt.get('vcodec') and fmt.get('vcodec') != 'none':
                            selected_format = fmt
                            video_url = fmt['url']
                            break
                    if selected_format:
                        logger.info("Selected video format from requested_formats: ID=%s, Resolution=%sx%s, FPS=%s", 
                                   selected_format.get('format_id', 'N/A'), 
                                   selected_format.get('width', 'N/A'), selected_format.get('height', 'N/A'), 
                                   selected_format.get('fps', 'N/A'))
                
                if not video_url and 'formats' in info and info['formats']:
                    # Filter formats to avoid HLS/DASH playlists and prefer direct URLs
                    def is_direct_url(fmt):
                        url = fmt.get('url', '')
                        # Avoid HLS (.m3u8) and DASH (.mpd) playlist URLs
                        return (url and 
                               not url.endswith('.m3u8') and 
                               not url.endswith('.mpd') and 
                               'manifest' not in url.lower() and
                               'playlist' not in url.lower())
                    
                    # Enhanced format selection with better quality prioritization
                    # First try: High quality formats (1080p+) with both video and audio (direct URLs)
                    video_formats = [f for f in info['formats'] 
                                   if f.get('vcodec') and f.get('vcodec') != 'none' 
                                   and f.get('acodec') and f.get('acodec') != 'none'
                                   and f.get('url')
                                   and f.get('height', 0) >= 1080
                                   and is_direct_url(f)]
                    
                    if not video_formats:
                        # Second try: Good quality formats (720p+) with both video and audio (direct URLs)
                        video_formats = [f for f in info['formats'] 
                                       if f.get('vcodec') and f.get('vcodec') != 'none' 
                                       and f.get('acodec') and f.get('acodec') != 'none'
                                       and f.get('url')
                                       and f.get('height', 0) >= 720
                                       and is_direct_url(f)]
                    
                    if not video_formats:
                        # Third try: Medium quality formats (480p+) with both video and audio (direct URLs)
                        video_formats = [f for f in info['formats'] 
                                       if f.get('vcodec') and f.get('vcodec') != 'none' 
                                       and f.get('acodec') and f.get('acodec') != 'none'
                                       and f.get('url')
                                       and f.get('height', 0) >= 480
                                       and is_direct_url(f)]
                    
                    if not video_formats:
                        # Fourth try: Any format with both video and audio (direct URLs only)
                        video_formats = [f for f in info['formats'] 
                                       if f.get('vcodec') and f.get('vcodec') != 'none' 
                                       and f.get('acodec') and f.get('acodec') != 'none'
                                       and f.get('url')
                                       and is_direct_url(f)]
                    
                    if not video_formats:
                        # Fifth try: High quality video-only formats (1080p+, direct URLs)
                        video_formats = [f for f in info['formats'] 
                                       if f.get('vcodec') and f.get('vcodec') != 'none'
                                       and f.get('url')
                                       and f.get('height', 0) >= 1080
                                       and is_direct_url(f)]
                    
                    if not video_formats:
                        # Sixth try: Good quality video-only formats (720p+, direct URLs)
                        video_formats = [f for f in info['formats'] 
                                       if f.get('vcodec') and f.get('vcodec') != 'none'
                                       and f.get('url')
                                       and f.get('height', 0) >= 720
                                       and is_direct_url(f)]
                    
                    if video_formats:
                        # Sort by quality (height * width * fps) - prioritize higher resolution
                        def format_quality(fmt):
                            height = fmt.get('height', 0) or 0
                            width = fmt.get('width', 0) or 0
                            fps = fmt.get('fps', 0) or 0
                            # Bonus for higher resolution
                            resolution_bonus = height * 2 if height >= 720 else 0
                            return (height * width * fps) + resolution_bonus
                        
                        selected_format = max(video_formats, key=format_quality)
                        video_url = selected_format['url']
                        logger.info("Selected best quality format: ID=%s, Resolution=%sx%s, FPS=%s, URL type=%s", 
                                   selected_format.get('format_id', 'N/A'), 
                                   selected_format.get('width', 'N/A'), selected_format.get('height', 'N/A'), 
                                   selected_format.get('fps', 'N/A'),
                                   'direct' if is_direct_url(selected_format) else 'playlist')
                
                if not video_url and 'url' in info:
                    video_url = info['url']
                    logger.info("Using direct video URL from info (fallback)")
                
                if not video_url:
                    raise RuntimeError("No suitable video URL found in extracted info")
                
                result = {
                    'title': info.get('title', 'video'),
                    'url': video_url,
                    'ext': info.get('ext', 'mp4'),
                    'filesize': info.get('filesize'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                    'headers': opts.get('http_headers', {})
                }
                
                logger.info("Info extraction successful using %s strategy: %s", strategy["name"], info.get('title', 'Unknown'))
                return result
                
        except Exception as e:
            error_msg = str(e).lower()
            last_error = e
            
            logger.warning("Strategy %s failed (attempt %d/%d): %s", 
                         strategy["name"], attempt, len(extraction_strategies), str(e))
            
            # Check if it's a 403 error and we have more strategies
            if "403" in error_msg or "forbidden" in error_msg:
                if attempt < len(extraction_strategies):
                    logger.info("Trying next extraction strategy...")
                    time.sleep(3)  # Longer wait between strategy changes
                    continue
                else:
                    logger.error("All extraction strategies failed with 403 errors")
            elif "private" in error_msg or "unavailable" in error_msg:
                # Video is private/unavailable - no point in retrying
                logger.error("Video is private or unavailable: %s", str(e))
                break
            else:
                # For other errors, try next strategy
                if attempt < len(extraction_strategies):
                    logger.info("Trying next extraction strategy due to error...")
                    time.sleep(2)
                    continue
                else:
                    break
    
    # If we get here, all strategies failed
    if "403" in str(last_error).lower() or "forbidden" in str(last_error).lower():
        raise RuntimeError(f"Download failed: All extraction methods blocked (403). This video requires authentication cookies or is geo-restricted. Please upload valid cookies via the admin panel. Last error: {last_error}")
    elif "private" in str(last_error).lower() or "unavailable" in str(last_error).lower():
        raise RuntimeError(f"Download failed: Video is private, deleted, or unavailable. Error: {last_error}")
    else:
        raise RuntimeError(f"Info extraction failed after trying {len(extraction_strategies)} extraction strategies. Last error: {last_error}")


def download_with_yt_dlp(url: str, platform: str, user_id: str = None) -> str:
    unique = uuid.uuid4().hex[:10]
    outtmpl = str(DOWNLOADS_DIR / f"{unique}_%(title)s.%(ext)s")
    
    # Multiple extraction strategies for better success rate
    extraction_strategies = [
        # Strategy 1: iOS client (often most reliable)
        {
            "name": "iOS Client",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "extractor_args": {
                "youtube": {
                    "player_client": "ios",
                    "skip": ["hls"],
                    "player_skip": ["webpage"]
                }
            }
        },
        # Strategy 2: Android client
        {
            "name": "Android Client",
            "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "android",
                    "skip": ["hls"],
                    "include_live_dash": False,
                    "player_skip": ["webpage"]
                }
            }
        },
        # Strategy 3: TV client (proven to work on command line)
        {
            "name": "TV Client",
            "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "tv",
                    "skip": ["hls"],
                    "include_live_dash": False,
                    "player_skip": ["configs", "webpage"]
                }
            }
        },
        # Strategy 4: TV Embedded client
        {
            "name": "TV Embedded Client",
            "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "tv_embedded",
                    "skip": ["hls"],
                    "player_skip": ["webpage"]
                }
            }
        },
        # Strategy 5: Web Music client
        {
            "name": "Web Music Client",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "web_music",
                    "skip": ["hls"],
                    "player_skip": ["webpage"]
                }
            }
        },
        # Strategy 6: Android Music client
        {
            "name": "Android Music Client",
            "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "android_music",
                    "skip": ["hls"],
                    "player_skip": ["webpage"]
                }
            }
        }
    ]
    
    last_error = None
    
    for attempt, strategy in enumerate(extraction_strategies, 1):
        try:
            opts = build_ydl_opts(outtmpl, platform, user_id)
            
            # Apply strategy-specific configurations
            opts["http_headers"]["User-Agent"] = strategy["user_agent"]
            if "extractor_args" in strategy:
                if "extractor_args" not in opts:
                    opts["extractor_args"] = {}
                opts["extractor_args"].update(strategy["extractor_args"])
            
            # Let build_ydl_opts format selection take effect (no override needed)
            
            # Add detailed format logging
            opts["listformats"] = False  # Don't list formats, but log selected format
            opts["verbose"] = True  # Enable verbose logging to see format selection
            
            logger.info("Download attempt %d/%d using %s strategy: %s (platform=%s)", 
                       attempt, len(extraction_strategies), strategy["name"], url, platform)
            
            # Debug: Log the exact extractor_args and format being used
            logger.info("Extractor args: %s", opts.get("extractor_args", {}))
            logger.info("Using format string: %s", opts.get("format", "default"))
            
            with YoutubeDL(opts) as ydl:
                # Direct download without double extraction
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("Failed to extract video info")
                
                # Log detailed format information
                if 'formats' in info and info['formats']:
                    logger.info("Available formats count: %d", len(info['formats']))
                    # Log details of top 3 formats for debugging
                    for i, fmt in enumerate(info['formats'][:3]):
                        logger.info("Format %d: ID=%s, Resolution=%sx%s, FPS=%s, VCodec=%s, ACodec=%s", 
                                   i+1, fmt.get('format_id', 'N/A'), 
                                   fmt.get('width', 'N/A'), fmt.get('height', 'N/A'),
                                   fmt.get('fps', 'N/A'), fmt.get('vcodec', 'N/A'), fmt.get('acodec', 'N/A'))
                
                # Log the selected format
                if 'requested_formats' in info:
                    for i, fmt in enumerate(info['requested_formats']):
                        logger.info("Selected format %d: ID=%s, Resolution=%sx%s, FPS=%s", 
                                   i+1, fmt.get('format_id', 'N/A'), 
                                   fmt.get('width', 'N/A'), fmt.get('height', 'N/A'), fmt.get('fps', 'N/A'))
                elif 'format_id' in info:
                    logger.info("Selected single format: ID=%s, Resolution=%sx%s, FPS=%s", 
                               info.get('format_id', 'N/A'), info.get('width', 'N/A'), 
                               info.get('height', 'N/A'), info.get('fps', 'N/A'))
                
                saved = ydl.prepare_filename(info)
                logger.info("Download successful using %s strategy: %s", strategy["name"], saved)
                return saved
                
        except Exception as e:
            error_msg = str(e).lower()
            last_error = e
            
            logger.warning("Strategy %s failed (attempt %d/%d): %s", 
                         strategy["name"], attempt, len(extraction_strategies), str(e))
            
            # Check if it's a 403 error and we have more strategies
            if "403" in error_msg or "forbidden" in error_msg:
                if attempt < len(extraction_strategies):
                    logger.info("Trying next extraction strategy...")
                    time.sleep(3)  # Longer wait between strategy changes
                    continue
                else:
                    logger.error("All extraction strategies failed with 403 errors")
            elif "private" in error_msg or "unavailable" in error_msg:
                # Video is private/unavailable - no point in retrying
                logger.error("Video is private or unavailable: %s", str(e))
                break
            else:
                # For other errors, try next strategy
                if attempt < len(extraction_strategies):
                    logger.info("Trying next extraction strategy due to error...")
                    time.sleep(2)
                    continue
                else:
                    break
    
    # If we get here, all strategies failed
    if "403" in str(last_error).lower() or "forbidden" in str(last_error).lower():
        raise RuntimeError(f"Download failed: All extraction methods blocked (403). This video requires authentication cookies or is geo-restricted. Please upload valid cookies via the admin panel. Last error: {last_error}")
    elif "private" in str(last_error).lower() or "unavailable" in str(last_error).lower():
        raise RuntimeError(f"Download failed: Video is private, deleted, or unavailable. Error: {last_error}")
    else:
        raise RuntimeError(f"Download failed after trying {len(extraction_strategies)} extraction strategies. Last error: {last_error}")


def stream_video_to_browser(video_info: dict):
    """Stream video content directly to browser without saving to disk"""
    try:
        video_url = video_info['url']
        headers = video_info.get('headers', {})
        title = video_info.get('title', 'video')
        ext = video_info.get('ext', 'mp4')
        
        # Clean filename for download
        safe_filename = secure_filename(f"{title}.{ext}")
        if not safe_filename:
            safe_filename = f"video.{ext}"
        
        logger.info(f"Starting stream for: {safe_filename}")
        
        def generate():
            try:
                # Add timeout and better error handling
                with requests.get(video_url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    logger.info(f"Successfully connected to video stream: {r.status_code}")
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            yield chunk
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error streaming video: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error streaming video: {e}")
                raise
        
        # Create response with appropriate headers
        response = Response(generate(), mimetype='application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        
        # Add content length if available
        if video_info.get('filesize'):
            response.headers['Content-Length'] = str(video_info['filesize'])
        
        return response
        
    except Exception as e:
        logger.error(f"Error in stream_video_to_browser: {e}")
        # Return error response
        return jsonify({"error": f"Failed to stream video: {str(e)}"}), 500


# -----------------------------
# Decorators: admin required
# -----------------------------
def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("admin_logged_in"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login", next=request.path))
    wrapped.__name__ = f.__name__
    return wrapped


# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    download_link = None
    error = None

    if request.method == "POST":
        url = (request.form.get("video_url") or "").strip()
        platform = (request.form.get("platform") or detect_platform(url)).strip().lower()

        if not url:
            flash("Please enter a video URL.", "error")
            return redirect(url_for("index"))

        # if platform is unknown, return helpful message
        if platform == "unknown":
            flash("Unsupported platform. Supported: YouTube, TikTok, Instagram.", "error")
            return redirect(url_for("index"))

        # If youtube and cookies missing, warn user in UI but still attempt download
        if platform == "youtube" and not COOKIES_PATH.exists():
            flash("No cookies.txt found. Restricted YouTube videos may fail. Upload cookies from Admin.", "warning")

        try:
            user_id = session.get('user_id')
            
            # For YouTube downloads, enforce cookie requirement with time validation
            if platform == "youtube":
                if not user_id:
                    flash("Please upload your cookies file first to download YouTube videos", "error")
                    return redirect(url_for("index"))
                
                if not are_cookies_valid(user_id):
                    flash(f"Your cookies have expired or are missing. Please upload a new cookies file. Cookies are valid for {COOKIES_VALIDITY_MINUTES} minutes after upload.", "error")
                    return redirect(url_for("index"))
            
            # Get video info and stream directly
            video_info = get_video_info_and_url(url, platform, user_id)
            
            # Record history
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "platform": platform,
                "url": url,
                "title": video_info.get('title', 'Unknown'),
                "uploader": video_info.get('uploader', 'Unknown')
            }
            append_history(entry)
            
            # Stream the video directly to browser
            return stream_video_to_browser(video_info)
        except Exception as e:
            logger.exception("Download failed")
            flash(f"Download failed: {e}", "error")
            return redirect(url_for("index"))

    history = load_history()
    return render_template("index.html", history=history)


@app.route("/cookie_status", methods=["GET"])
def cookie_status():
    """Get current cookie validity status for the user"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"valid": False, "message": "No user session"})
    
    if are_cookies_valid(user_id):
        try:
            # Get remaining time
            timestamp_file = BASE_DIR / "cookies" / user_id / "upload_timestamp.json"
            with timestamp_file.open("r", encoding="utf-8") as f:
                timestamp_data = json.load(f)
            
            upload_time = datetime.fromisoformat(timestamp_data["upload_time"])
            current_time = datetime.utcnow()
            elapsed_seconds = (current_time - upload_time).total_seconds()
            remaining_seconds = (COOKIES_VALIDITY_MINUTES * 60) - elapsed_seconds
            
            return jsonify({
                "valid": True,
                "remaining_seconds": max(0, int(remaining_seconds)),
                "message": f"Cookies valid for {max(0, int(remaining_seconds/60))} more minutes"
            })
        except Exception as e:
            logger.warning(f"Failed to get cookie timing info: {e}")
            return jsonify({"valid": True, "message": "Cookies are valid"})
    else:
        return jsonify({"valid": False, "message": "Cookies expired or missing"})


@app.route("/upload_cookies", methods=["POST"])
def upload_cookies():
    """
    Allow users to upload their own cookies.txt for YouTube downloads
    """
    file = request.files.get("cookies")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".txt"):
        return jsonify({"error": "Please upload a .txt cookies file"}), 400

    try:
        # Create user-specific cookies directory
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
        
        user_cookies_dir = BASE_DIR / "cookies" / user_id
        user_cookies_dir.mkdir(parents=True, exist_ok=True)
        user_cookies_path = user_cookies_dir / "cookies.txt"
        
        # Save cookies file
        tmp_path = user_cookies_path.with_suffix(".tmp")
        file.save(tmp_path)
        tmp_path.replace(user_cookies_path)
        
        # Save upload timestamp for validity tracking
        save_cookie_timestamp(user_id)
        
        logger.info(f"User {user_id} uploaded cookies.txt")
        return jsonify({"success": True, "message": f"Cookies uploaded successfully! Valid for {COOKIES_VALIDITY_MINUTES} minutes. You can now download restricted YouTube videos."})
    except Exception as e:
        logger.exception("Failed to save user cookies")
        return jsonify({"error": f"Failed to save cookies: {e}"}), 500


@app.route("/test_video", methods=["POST"])
def test_video():
    """Test if a video is available for download without actually downloading it"""
    try:
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"error": "URL is required"}), 400
        
        url = data["url"].strip()
        if not url:
            return jsonify({"error": "URL cannot be empty"}), 400
        
        platform = detect_platform(url)
        user_id = session.get("user_id")
        
        # For YouTube, check if cookies are required
        if platform == "youtube" and not user_id:
            return jsonify({
                "error": "Please upload your cookies file first to test YouTube videos",
                "requires_cookies": True
            }), 400
        
        logger.info("Testing video availability: %s (platform=%s)", url, platform)
        
        # Try to extract basic info without downloading
        try:
            video_info = get_video_info_and_url(url, platform, user_id)
            return jsonify({
                "available": True,
                "title": video_info.get("title", "Unknown"),
                "duration": video_info.get("duration"),
                "uploader": video_info.get("uploader"),
                "platform": platform,
                "message": "Video is available for download"
            })
        except Exception as e:
            error_msg = str(e).lower()
            if "private" in error_msg or "unavailable" in error_msg:
                return jsonify({
                    "available": False,
                    "error": "Video is private, deleted, or unavailable",
                    "platform": platform
                })
            elif "403" in error_msg or "forbidden" in error_msg:
                return jsonify({
                    "available": False,
                    "error": "Video is geo-restricted or requires authentication",
                    "platform": platform,
                    "suggestion": "Try uploading fresh cookies or using a VPN"
                })
            else:
                return jsonify({
                    "available": False,
                    "error": f"Cannot access video: {str(e)}",
                    "platform": platform
                })
    
    except Exception as e:
        logger.error("Error testing video: %s", str(e))
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route("/download", methods=["POST"])
def download():
    """API endpoint for AJAX download requests"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        url = data.get("url", "").strip()
        platform = data.get("platform", "").strip().lower()
        
        if not url:
            return jsonify({"error": "Please provide a video URL"}), 400
            
        if not platform:
            platform = detect_platform(url)
            
        if platform == "unknown":
            return jsonify({"error": "Unsupported platform. Supported: YouTube, TikTok, Instagram"}), 400
            
        # For YouTube downloads, enforce cookie requirement with time validation
        user_id = session.get('user_id')
        if platform == "youtube":
            if not user_id:
                return jsonify({"error": "Please upload your cookies file first to download YouTube videos"}), 400
            
            if not are_cookies_valid(user_id):
                return jsonify({"error": f"Your cookies have expired or are missing. Please upload a new cookies file. Cookies are valid for {COOKIES_VALIDITY_MINUTES} minutes after upload."}), 400
            
        try:
            # Get video info and stream directly
            video_info = get_video_info_and_url(url, platform, user_id)
            
            # Record history
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "platform": platform,
                "url": url,
                "title": video_info.get('title', 'Unknown'),
                "uploader": video_info.get('uploader', 'Unknown')
            }
            append_history(entry)
            
            # Stream the video directly to browser
            return stream_video_to_browser(video_info)
            
        except Exception as e:
            logger.exception("Failed to get video info or stream")
            return jsonify({"error": str(e)}), 500
        
    except Exception as e:
        logger.exception("Download failed via API")
        return jsonify({"error": str(e)}), 500


# @app.route("/downloads/<path:filename>")
# def download_file(filename):
#     # This route is no longer needed since we stream videos directly
#     # safe = secure_filename(filename)
#     # file_path = DOWNLOADS_DIR / safe
#     # if not file_path.exists():
#     #     abort(404)
#     # return send_from_directory(str(DOWNLOADS_DIR), safe, as_attachment=True)
#     abort(404)  # Files are no longer saved to disk


# -----------------------------
# Admin UI + API
# -----------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Admin logged in", "success")
            nxt = request.args.get("next") or url_for("admin")
            return redirect(nxt)
        else:
            flash("Invalid password", "error")
            return redirect(url_for("admin_login"))
    return render_template("admin_login.html")


@app.route("/admin/logout")
@require_admin
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out", "info")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
@require_admin
def admin():
    cookies_present = COOKIES_PATH.exists()
    cookies_mtime = None
    if cookies_present:
        cookies_mtime = datetime.utcfromtimestamp(COOKIES_PATH.stat().st_mtime).isoformat()
    return render_template("admin.html", cookies_present=cookies_present, cookies_mtime=cookies_mtime)


@app.route("/admin/upload_cookies", methods=["POST"])
@require_admin
def admin_upload_cookies():
    """
    Upload cookies.txt via the admin UI. Field name: 'cookies'
    """
    file = request.files.get("cookies")
    if not file:
        flash("No file uploaded", "error")
        return redirect(url_for("admin"))

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".txt"):
        flash("Please upload a .txt cookies file", "error")
        return redirect(url_for("admin"))

    try:
        # save atomically
        tmp_path = COOKIES_PATH.with_suffix(".tmp")
        file.save(tmp_path)
        tmp_path.replace(COOKIES_PATH)
        flash("cookies.txt uploaded successfully! You can now download restricted videos.", "success")
        logger.info("Admin uploaded cookies.txt")
        return redirect(url_for("index"))
    except Exception as e:
        logger.exception("Failed to save cookies")
        flash(f"Failed to save cookies: {e}", "error")
        return redirect(url_for("admin"))


@app.route("/admin/delete_cookies", methods=["POST"])
@require_admin
def admin_delete_cookies():
    try:
        if COOKIES_PATH.exists():
            COOKIES_PATH.unlink()
            flash("cookies.txt removed", "success")
        else:
            flash("No cookies.txt to remove", "info")
    except Exception as e:
        logger.exception("Failed to remove cookies")
        flash("Failed to remove cookies", "error")
    return redirect(url_for("admin"))


# -----------------------------
# Optional: API endpoint for automated sync script
# -----------------------------
@app.route("/api/upload_cookies", methods=["POST"])
def api_upload_cookies():
    """
    POST cookies file with form-data 'file' and header 'X-Upload-Token' set to API_UPLOAD_TOKEN.
    Use this for automated sync from your local machine (cron job).
    """
    token = request.headers.get("X-Upload-Token", "") or request.form.get("token", "")
    if not API_UPLOAD_TOKEN:
        return jsonify({"error": "API upload not enabled"}), 403
    if token != API_UPLOAD_TOKEN:
        return jsonify({"error": "Invalid upload token"}), 403

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400

    # Save
    try:
        tmp = COOKIES_PATH.with_suffix(".tmp")
        f.save(tmp)
        tmp.replace(COOKIES_PATH)
        logger.info("API uploaded cookies.txt via token")
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Failed to save cookies via API")
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Error handlers
# -----------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", history=load_history(), error="Page not found"), 404


@app.errorhandler(500)
def internal_err(e):
    return render_template("index.html", history=load_history(), error="Internal server error"), 500


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    logger.info("Starting VideoCatcher app (dev server). Use gunicorn + nginx in production.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
