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
    session, jsonify, send_from_directory, abort
)
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
FLASK_SECRET = os.getenv("FLASK_SECRET", uuid.uuid4().hex)

# Ensure folders exist
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
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


_cleanup_thread = threading.Thread(target=cleanup_old_files_loop, args=(DOWNLOADS_DIR, DOWNLOAD_TTL_MINUTES), daemon=True)
_cleanup_thread.start()

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


def build_ydl_opts(output_template: str, platform: str):
    base = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": "/app/.cache",
        "no_check_certificate": True,
        "http_headers": {}
    }

    # Platform-specific configurations
    if platform == "youtube":
        base["format"] = "best[height<=1080]/bestvideo[height<=1080]+bestaudio/best"
    elif platform == "tiktok":
        base["format"] = "best"
    elif platform == "instagram":
        base["format"] = "best"
    else:
        base["format"] = "best"

    # use cookies file if present (critical for restricted content)
    if COOKIES_PATH.exists():
        base["cookiefile"] = str(COOKIES_PATH)
        logger.info("Using cookies file: %s", COOKIES_PATH)
    else:
        logger.warning("No cookies file found - some videos may be restricted")

    return base


def download_with_yt_dlp(url: str, platform: str) -> str:
    unique = uuid.uuid4().hex[:10]
    outtmpl = str(DOWNLOADS_DIR / f"{unique}_%(title)s.%(ext)s")
    
    # Multiple extraction strategies for better success rate
    extraction_strategies = [
        # Strategy 1: TV client (proven to work on command line)
        {
            "name": "TV Client",
            "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "tv",
                    "skip": ["hls"],
                    "include_live_dash": False,
                    "player_skip": ["configs"]
                }
            }
        },
        {
            "name": "Android Client",
            "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": "android",
                    "skip": ["hls"],
                    "include_live_dash": False
                }
            }
        },
        {
            "name": "iOS Client",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "extractor_args": {
                "youtube": {
                    "player_client": "ios",
                    "skip": ["hls"]
                }
            }
        }
    ]
    
    last_error = None
    
    for attempt, strategy in enumerate(extraction_strategies, 1):
        try:
            opts = build_ydl_opts(outtmpl, platform)
            
            # Apply strategy-specific configurations
            opts["http_headers"]["User-Agent"] = strategy["user_agent"]
            if "extractor_args" in strategy:
                if "extractor_args" not in opts:
                    opts["extractor_args"] = {}
                opts["extractor_args"].update(strategy["extractor_args"])
            
            # For YouTube, add strategy-specific optimizations
            if platform == "youtube":
                if "Mobile" in strategy["name"]:
                    opts["format"] = "best[height<=720]/worst"  # Mobile-friendly format
                elif "TV" in strategy["name"]:
                    opts["format"] = "best[height<=1080]"  # TV format
                else:
                    opts["format"] = "best[height<=1080]/bestvideo[height<=1080]+bestaudio/best"
            
            logger.info("Download attempt %d/%d using %s strategy: %s (platform=%s)", 
                       attempt, len(extraction_strategies), strategy["name"], url, platform)
            
            # Debug: Log the exact extractor_args being used
            logger.info("Extractor args: %s", opts.get("extractor_args", {}))
            
            with YoutubeDL(opts) as ydl:
                # Direct download without double extraction
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("Failed to extract video info")
                
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
            saved_path = download_with_yt_dlp(url, platform)
            filename = os.path.basename(saved_path)
            download_link = url_for("download_file", filename=filename)

            # record history
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "platform": platform,
                "url": url,
                "filename": filename,
            }
            append_history(entry)
            flash("Download completed!", "success")
            return redirect(download_link)
        except Exception as e:
            logger.exception("Download failed")
            flash(f"Download failed: {e}", "error")
            return redirect(url_for("index"))

    history = load_history()
    return render_template("index.html", history=history)


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
            
        # Download the video
        saved_path = download_with_yt_dlp(url, platform)
        filename = os.path.basename(saved_path)
        download_link = url_for("download_file", filename=filename)
        
        # Record history
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "platform": platform,
            "url": url,
            "filename": filename,
        }
        append_history(entry)
        
        return jsonify({
            "success": True,
            "download_link": download_link,
            "filename": filename,
            "title": filename  # You could extract title from yt-dlp info if needed
        })
        
    except Exception as e:
        logger.exception("Download failed via API")
        return jsonify({"error": str(e)}), 500


@app.route("/downloads/<path:filename>")
def download_file(filename):
    safe = secure_filename(filename)
    file_path = DOWNLOADS_DIR / safe
    if not file_path.exists():
        abort(404)
    return send_from_directory(str(DOWNLOADS_DIR), safe, as_attachment=True)


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
