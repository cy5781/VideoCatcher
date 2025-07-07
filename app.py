from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import yt_dlp
import os
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

DOWNLOADS_FOLDER = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)




def download_video(url, output_path):
    # Generate a unique ID to avoid overwriting files with the same name
    unique_id = uuid.uuid4().hex[:8]
    temp_filename = f"{unique_id}_%(title)s.%(ext)s"
    outtmpl_path = os.path.join(output_path, temp_filename)

    ydl_opts = {
        'outtmpl': outtmpl_path,
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'cookiesfrombrowser': ('chrome',),  # <-- This line is key
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_filename = ydl.prepare_filename(info)
        final_filename = os.path.basename(downloaded_filename)
        return final_filename  # Return relative path

@app.route('/', methods=['GET', 'POST'])
def index():
    download_link = None
    if request.method == 'POST':
        video_url = request.form['video_url'].strip()
        if not video_url:
            flash("Please enter a valid video URL.", "error")
            return redirect(url_for('index'))

        try:
            final_filename = download_video(video_url, DOWNLOADS_FOLDER)
            flash("Video downloaded successfully!", "success")
            download_link = url_for('download_file', filename=final_filename)
        except Exception as e:
            flash(f"Download failed: {e}", "error")
            return redirect(url_for('index'))

    return render_template('index.html', download_link=download_link)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(DOWNLOADS_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
