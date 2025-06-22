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

@app.route('/')
def index():
    return render_template('index.html')

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
    from playwright_bridge import get_streams_with_playwright
    import os
    # 1. Try Playwright first
    pw_result = get_streams_with_playwright(url)
    if pw_result and not pw_result.get('error') and (pw_result.get('video_urls') or pw_result.get('audio_urls')):
        # Return Playwright streams as pseudo-formats
        formats = []
        for i, vurl in enumerate(pw_result.get('video_urls', [])):
            formats.append({
                'format_id': f'pwvideo{i}',
                'ext': 'mp4',
                'format_note': 'Playwright Video',
                'resolution': '',
                'filesize': 0,
                'direct_url': vurl
            })
        for i, aurl in enumerate(pw_result.get('audio_urls', [])):
            formats.append({
                'format_id': f'pwaudio{i}',
                'ext': 'm4a',
                'format_note': 'Playwright Audio',
                'resolution': '',
                'filesize': 0,
                'direct_url': aurl
            })
        return jsonify({'title': pw_result.get('title', ''), 'formats': formats})
    # 2. Fallback to yt-dlp as before
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'S': 'vcodec:h264,res:720,acodec:aac',
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    # If Playwright returned a PO Token, pass it to yt-dlp
    extractor_args = {}
    if pw_result and pw_result.get('po_token'):
        extractor_args['youtube'] = {'po_token': f"mweb.gvs+{pw_result['po_token']}"}
    if extractor_args:
        ydl_opts['extractor_args'] = extractor_args
    # Set user-agent to match Playwright's browser
    if pw_result and pw_result.get('user_agent'):
        ydl_opts['user_agent'] = pw_result['user_agent']
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            allowed_heights = [2160, 1440, 1080, 720, 480, 360]
            allowed_resolutions = [f"{h}p" for h in allowed_heights]
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
            return jsonify({'error': f'Both Playwright and yt-dlp failed: {e}'}), 400

import redis
import ffmpeg

# Connect to Redis (external if env vars set, else local, with optional auth)
REDIS_HOST = os.environ.get('REDIS_HOST')
if not REDIS_HOST or not REDIS_HOST.strip():
    REDIS_HOST = 'localhost'
def get_int_env(varname, default):
    try:
        value = os.environ.get(varname, str(default))
        return int(value) if value.strip() else default
    except Exception:
        return default

REDIS_PORT = get_int_env('REDIS_PORT', 6379)
REDIS_DB = get_int_env('REDIS_DB', 0)
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
    direct_url = request.form.get('direct_url')
    temp_dir = tempfile.mkdtemp()
    cache_key = f"merged:{url}:{format_id}:{direct_url}"
    cached = redis_client.get(cache_key)
    if cached:
        merged_path = os.path.join(temp_dir, 'merged.mp4')
        with open(merged_path, 'wb') as f:
            f.write(cached)
        return send_file(merged_path, as_attachment=True)
    # If direct_url is present (Playwright), download it directly
    if direct_url:
        import requests
        local_file = os.path.join(temp_dir, 'downloaded.mp4')
        # Playwright cookie support
        cookies = None
        if os.path.exists('cookies.txt'):
            with open('cookies.txt', 'r', encoding='utf-8') as f:
                cookies = f.read()
        headers = {}
        if cookies:
            headers['Cookie'] = cookies
        with requests.get(direct_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(local_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        with open(local_file, 'rb') as f:
            redis_client.setex(cache_key, 86400, f.read())
        return send_file(local_file, as_attachment=True)
    # Fallback: yt-dlp logic as before
    ydl_base_opts = {
        'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'merge_output_format': 'mp4',
    }
    if os.path.exists('cookies.txt'):
        ydl_base_opts['cookiefile'] = 'cookies.txt'
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
        selected_format = None
        for fmt in info_dict.get('formats', []):
            if str(fmt.get('format_id')) == str(format_id):
                selected_format = fmt
                break
        is_video_only = selected_format and selected_format.get('vcodec') != 'none' and selected_format.get('acodec') == 'none'
        if is_video_only:
            video_format = format_id
            audio_format = None
            best_audio = None
            for fmt in info_dict.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    if not best_audio or (fmt.get('abr', 0) > best_audio.get('abr', 0)):
                        best_audio = fmt
            if best_audio:
                audio_format = best_audio['format_id']
            ydl_opts = ydl_base_opts.copy()
            ydl_opts['format'] = f"{video_format}+{audio_format}" if audio_format else video_format
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_file = None
                audio_file = None
                for entry in info.get('requested_downloads', []):
                    if entry.get('vcodec') != 'none' and entry.get('acodec') == 'none':
                        video_file = entry['filepath']
                    elif entry.get('acodec') != 'none' and entry.get('vcodec') == 'none':
                        audio_file = entry['filepath']
                merged_file = os.path.join(temp_dir, 'merged.mp4')
                if video_file and audio_file:
                    (
                        ffmpeg
                        .input(video_file)
                        .input(audio_file)
                        .output(merged_file, vcodec='copy', acodec='copy', strict='experimental')
                        .run(overwrite_output=True)
                    )
                    with open(merged_file, 'rb') as f:
                        redis_client.setex(cache_key, 86400, f.read())
                    return send_file(merged_file, as_attachment=True)
                else:
                    return jsonify({'error': 'Failed to download or merge video/audio.'}), 500
        ydl_opts = ydl_base_opts.copy()
        ydl_opts['format'] = format_id
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            out_file = info['requested_downloads'][0]['filepath']
            with open(out_file, 'rb') as f:
                redis_client.setex(cache_key, 86400, f.read())
            return send_file(out_file, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


import subprocess
import json

@app.route('/api/get_streams', methods=['POST'])
def api_get_streams():
    url = request.form.get('url') or request.json.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        result = subprocess.run([
            'python', 'playwright_bridge.py', url
        ], capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            return jsonify({'error': result.stderr.strip() or 'Playwright script error'}), 500
        # Try to parse JSON from output
        try:
            data = json.loads(result.stdout.replace("'", '"'))  # crude fix for single quotes
            return jsonify(data)
        except Exception:
            return jsonify({'error': 'Could not parse Playwright output', 'raw': result.stdout}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Playwright script timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
