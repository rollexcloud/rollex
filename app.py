import os
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import yt_dlp
import tempfile

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-this-secret')


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

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
    ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': False}
    import os
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            formats = [
                {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'format_note': f.get('format_note', ''),
                    'resolution': f.get('resolution', ''),
                    'filesize': f.get('filesize', 0)
                } for f in info.get('formats', []) if f.get('filesize')
            ]
            return jsonify({'title': info.get('title', ''), 'formats': formats})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    format_id = request.form.get('format_id')
    temp_dir = tempfile.mkdtemp()
    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
    }
    import os
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return send_file(filename, as_attachment=True)
        except Exception as e:
            return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
