from flask import Flask, render_template, request, redirect, url_for, flash
import yt_dlp
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Needed for flashing messages

DOWNLOADS_FOLDER = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

def download_video(url, output_path):
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form['video_url'].strip()
        if not video_url:
            flash("Please enter a valid video URL.", "error")
            return redirect(url_for('index'))

        try:
            download_video(video_url, DOWNLOADS_FOLDER)
            flash("Video downloaded successfully!", "success")
        except Exception as e:
            flash(f"Download failed: {e}", "error")

        return redirect(url_for('index'))

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
