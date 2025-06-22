import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import yt_dlp
import ffmpeg
import redis
import tempfile

# Load .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-this-secret')


import os
from functools import wraps
from flask import session, abort

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')

# Simple decorator for admin auth
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('admin_logged_in'):
            return f(*args, **kwargs)
        return abort(403)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_upload_cookies'))
        return render_template('admin_login.html', error='Invalid password')
    return render_template('admin_login.html')

@app.route('/admin/upload_cookies', methods=['GET', 'POST'])
@admin_required
def admin_upload_cookies():
    if request.method == 'POST':
        file = request.files.get('cookies')
        if file and file.filename.endswith('.txt'):
            file.save('cookies.txt')
            return render_template('admin_upload_cookies.html', success=True)
        return render_template('admin_upload_cookies.html', error='Invalid file')
    return render_template('admin_upload_cookies.html')

@app.route('/get_formats', methods=['POST'])
def get_formats():
    url = request.form.get('url')
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'S': 'vcodec:h264,res:720,acodec:aac',
    }
    import os
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            print("[yt-dlp] Full info dict:")
            print(info)
            print("[yt-dlp] All formats:")
            for f in info.get('formats', []):
                print(f)
            allowed_heights = [2160, 1440, 1080, 720, 480, 360]
            allowed_resolutions = [f"{h}p" for h in allowed_heights]
            # Video formats with allowed resolutions or heights
            video_formats = [
                {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'format_note': f.get('format_note', ''),
                    'resolution': f.get('resolution', '') or (f"{f.get('height', '')}p" if f.get('height') else ''),
                    'filesize': f.get('filesize', 0)
                }
                for f in info.get('formats', [])
                if f.get('vcodec') != 'none' and (
                    (f.get('height') and f.get('height') in allowed_heights) or
                    (f.get('resolution', '') in allowed_resolutions)
                )
            ]
            # Audio-only formats
            audio_formats = [
                {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'format_note': f.get('format_note', 'Audio only') or 'Audio only',
                    'resolution': '',
                    'filesize': f.get('filesize', 0)
                }
                for f in info.get('formats', [])
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none'
            ]
            formats = video_formats + audio_formats
            return jsonify({'title': info.get('title', ''), 'formats': formats})
        except Exception as e:
            print(f"[yt-dlp ERROR] {e}")
            return jsonify({'error': str(e)}), 400

import redis
import ffmpeg

# Connect to Redis (external if env vars set, else local, with optional auth)
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_USERNAME = os.environ.get('REDIS_USERNAME')
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD')
redis_kwargs = {'host': REDIS_HOST, 'port': REDIS_PORT, 'db': REDIS_DB}
if REDIS_USERNAME:
    redis_kwargs['username'] = REDIS_USERNAME
if REDIS_PASSWORD:
    redis_kwargs['password'] = REDIS_PASSWORD
redis_client = redis.Redis(**redis_kwargs)

@app.route('/download', methods=['POST'])
def download():
    import os
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    temp_dir = tempfile.mkdtemp()
    cache_key = f"merged:{url}:{format_id}"
    cached = redis_client.get(cache_key)
    if cached:
        # Serve cached merged file from Redis
        merged_path = os.path.join(temp_dir, 'merged.mp4')
        with open(merged_path, 'wb') as f:
            f.write(cached)
        return send_file(merged_path, as_attachment=True)
    # Download video/audio separately if needed
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'format': format_id,
        'merge_output_format': 'mp4',
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Try to find merged file (yt-dlp may merge automatically)
            filename = ydl.prepare_filename(info)
            merged_file = filename
            # If video-only or audio-only, or if format_id contains '+', merge manually
            if '+' in format_id or (info.get('requested_downloads') and len(info['requested_downloads']) > 1):
                # Find video and audio files
                video_file = None
                audio_file = None
                for entry in info.get('requested_downloads', []):
                    if entry.get('vcodec') != 'none' and entry.get('acodec') == 'none':
                        video_file = entry['filepath']
                    if entry.get('acodec') != 'none' and entry.get('vcodec') == 'none':
                        audio_file = entry['filepath']
                if video_file and audio_file:
                    merged_file = os.path.join(temp_dir, 'merged.mp4')
                    (
                        ffmpeg
                        .input(video_file)
                        .input(audio_file)
                        .output(merged_file, vcodec='copy', acodec='copy', strict='experimental')
                        .run(overwrite_output=True)
                    )
            # Cache merged file in Redis
            with open(merged_file, 'rb') as f:
                redis_client.set(cache_key, f.read(), ex=24*3600)  # Cache for 24h
            return send_file(merged_file, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
