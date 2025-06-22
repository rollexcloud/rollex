import os
import yt_dlp
import tempfile
import ffmpeg
import redis
from rq import get_current_job

# Connect to Redis (reuse .env logic)
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

def download_and_merge(url, format_id, cache_key):
    job = get_current_job()
    temp_dir = tempfile.mkdtemp()
    progress_key = f"progress:{job.id}"
    file_key = f"progress:{job.id}:file"
    try:
        def hook(d):
            if d['status'] == 'downloading':
                percent = 0
                if d.get('total_bytes'):
                    percent = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
                elif d.get('total_bytes_estimate'):
                    percent = int(d['downloaded_bytes'] / d['total_bytes_estimate'] * 100)
                redis_client.set(progress_key, f"downloading:{percent}")
            elif d['status'] == 'finished':
                redis_client.set(progress_key, "merging")
        # Step 1: Download
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'format': format_id,
            'merge_output_format': 'mp4',
            'progress_hooks': [hook],
        }
        info = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        # Step 2: Merge if needed (handled by yt-dlp, but can check here)
        merged_file = filename
        redis_client.set(progress_key, "ready")
        redis_client.set(file_key, merged_file)
        # Step 3: Cache merged file
        with open(merged_file, 'rb') as f:
            redis_client.set(cache_key, f.read(), ex=24*3600)
        return merged_file
    except Exception as e:
        redis_client.set(progress_key, f'error:{str(e)}')
        raise
