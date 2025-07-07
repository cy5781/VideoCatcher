import sys
import yt_dlp

def download_video(url, output_path='.'):
    # Set up yt-dlp options:
    # The 'format' option uses "bestvideo+bestaudio" for separate streams if FFmpeg is available,
    # or falls back to "best" (progressive download) if necessary.
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        # 'merge_output_format' tells yt-dlp to merge separate streams; requires FFmpeg.
        'merge_output_format': 'mp4',
        'noplaylist': True,  # Only download a single video even if URL is a playlist.
        'verbose': True,     # Enable detailed logging; remove if not needed.
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            print(f"Downloading from URL: {url}")
            ydl.download([url])
            print("Download completed successfully!")
        except Exception as e:
            print(f"Error during download: {e}")
            sys.exit(1)

if __name__ == "__main__":
    # Check if the video URL is provided as a command-line argument.
    if len(sys.argv) > 1:
        video_url = sys.argv[1]
    else:
        video_url = input("Enter the YouTube video or Shorts URL: ").strip()

    download_video(video_url)
