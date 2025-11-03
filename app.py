from flask import Flask, render_template, request, send_file, jsonify, after_this_request, Response
import yt_dlp
import os
import tempfile
import shutil
import threading
import time

app = Flask(__name__, static_folder='static', template_folder='templates')

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

ALLOWED_DOMAINS = ("youtube.com", "youtu.be")
DOWNLOADS = {}  # {task_id: {"progress": int, "status": str, "filepath": str, "error": str}}

def is_allowed_url(url: str) -> bool:
    if not url or not url.startswith(('http://', 'https://')):
        return False
    return any(domain in url for domain in ALLOWED_DOMAINS)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/formats', methods=['POST'])
def get_formats():
    """Return available video/audio formats for a given URL."""
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not is_allowed_url(url):
        return jsonify({'error': 'Invalid or unsupported URL.'}), 400

    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        video_formats = []
        audio_formats = []

        for f in info.get('formats', []):
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                video_formats.append({
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f.get('resolution') or f"{f.get('height','?')}p",
                    'filesize': f.get('filesize')
                })
            elif f.get('vcodec') != 'none':
                video_formats.append({
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f.get('resolution') or f"{f.get('height','?')}p",
                    'filesize': f.get('filesize')
                })
            elif f.get('acodec') != 'none':
                audio_formats.append({
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'abr': f.get('abr', '?'),
                    'filesize': f.get('filesize')
                })

        return jsonify({
            'title': info.get('title'),
            'thumbnail': info.get('thumbnail'),
            'video_formats': video_formats,
            'audio_formats': audio_formats
        })

    except Exception as e:
        return jsonify({'error': f'Failed to fetch formats: {str(e)}'}), 500


def run_download(task_id, url, fmt, format_id):
    tmpdir = tempfile.mkdtemp(prefix="ydl_")
    DOWNLOADS[task_id] = {"progress": 0, "status": "downloading"}

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded / total * 100) if total else 0
            DOWNLOADS[task_id]["progress"] = percent
        elif d["status"] == "finished":
            DOWNLOADS[task_id]["progress"] = 95

    # Safe base options
    ydl_opts = {
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        if fmt == "mp3":
            # Force best available audio, no matter what
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192" if "128" in (format_id or "") else "320",
                }]
            })
        else:
            # Video mode: merge best video + audio automatically
            if format_id in ["1080p", "480p"]:
                # force these resolutions
                if format_id == "1080p":
                    ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best"
                elif format_id == "480p":
                    ydl_opts["format"] = "bestvideo[height<=480]+bestaudio/best"
            else:
                ydl_opts["format"] = "bestvideo+bestaudio/best"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Wait a bit for postprocessing to complete
        for _ in range(10):
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
            if files:
                break
            time.sleep(0.5)

        if not files:
            DOWNLOADS[task_id]["status"] = "error"
            DOWNLOADS[task_id]["error"] = "No file produced."
            return

        files.sort(key=lambda p: os.path.getsize(p), reverse=True)
        filepath = files[0]

        DOWNLOADS[task_id]["filepath"] = filepath
        DOWNLOADS[task_id]["status"] = "finished"
        DOWNLOADS[task_id]["progress"] = 100

    except Exception as e:
        DOWNLOADS[task_id]["status"] = "error"
        DOWNLOADS[task_id]["error"] = str(e)



@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    fmt = data.get('format', 'mp4')
    quality = data.get('quality', 'best')
    task_id = data.get('task_id')

    if not task_id:
        return jsonify({'error': 'Missing task id'}), 400

    if not is_allowed_url(url):
        return jsonify({'error': 'Invalid or unsupported URL.'}), 400

    DOWNLOADS[task_id] = {'progress': 0, 'status': 'starting', 'filepath': None, 'error': None}
    threading.Thread(target=run_download, args=(task_id, url, fmt, quality), daemon=True).start()

    return jsonify({'task_id': task_id})


@app.route('/progress/<task_id>')
def progress(task_id):
    def generate():
        while True:
            task = DOWNLOADS.get(task_id)
            if not task:
                yield 'data: {"status":"error","message":"Invalid task id"}\n\n'
                break
            yield f'data: {{"progress": {task["progress"]}, "status": "{task["status"]}"}}\n\n'
            if task['status'] in ('finished', 'error'):
                break
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')


@app.route('/fetch/<task_id>')
def fetch(task_id):
    task = DOWNLOADS.get(task_id)
    if not task:
        return "Invalid task id", 404
    
    filepath = task.get('filepath')
    if not filepath or not os.path.exists(filepath):
        print(f"[DEBUG] Missing file for task {task_id}: {filepath}")
        return "Not Found", 404

    filepath = task['filepath']
    tmpdir = task.get('tmpdir')

    @after_this_request
    def cleanup(response):
        try:
            if tmpdir and os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            DOWNLOADS.pop(task_id, None)
        except Exception:
            pass
        return response

    return send_file(filepath, as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))




# First Code (Only for learning)

# from flask import Flask, render_template, request, send_file, jsonify, after_this_request
# import yt_dlp
# import os
# import tempfile
# import shutil
# import validators

# app = Flask(__name__, static_folder='static', template_folder='templates')

# # Allow only YouTube URLs
# ALLOWED_DOMAINS = ("youtube.com", "youtu.be")

# def is_allowed_url(url: str) -> bool:
#     """Basic allowlist validation for YouTube links."""
#     if not url or not url.startswith(('http://', 'https://')):
#         return False
#     return any(domain in url for domain in ALLOWED_DOMAINS)


# @app.route('/')
# def index():
#     return render_template('index.html')


# @app.route('/download', methods=['POST'])
# def download():
#     data = request.get_json() or {}
#     url = data.get('url', '').strip()
#     fmt = data.get('format', 'mp4')

#     if not is_allowed_url(url):
#         return jsonify({'error': 'Invalid or unsupported URL.'}), 400

#     tmpdir = tempfile.mkdtemp(prefix='ydl_')

#     try:
#         # yt-dlp options
#         ydl_opts = {
#             'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
#             'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
#             'noplaylist': True,
#             'quiet': True,
#             'no_warnings': True,
#         }

#         # MP3 conversion options
#         if fmt == 'mp3':
#             ydl_opts.update({
#                 'format': 'bestaudio/best',
#                 'postprocessors': [{
#                     'key': 'FFmpegExtractAudio',
#                     'preferredcodec': 'mp3',
#                     'preferredquality': '192',
#                 }]
#             })

#         # Download video/audio
#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=True)

#         # Find the downloaded file
#         files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if os.path.isfile(os.path.join(tmpdir, f))]
#         if not files:
#             return jsonify({'error': 'Download failed or produced no file.'}), 500

#         files.sort(key=lambda p: os.path.getsize(p), reverse=True)
#         filepath = files[0]

#         # Cleanup AFTER response is fully sent
#         @after_this_request
#         def cleanup(response):
#             try:
#                 shutil.rmtree(tmpdir)
#             except Exception:
#                 pass
#             return response

#         # Send the file to client
#         return send_file(filepath, as_attachment=True)

#     except yt_dlp.utils.DownloadError as e:
#         return jsonify({'error': f'Download failed: {str(e)}'}), 500
#     except Exception as e:
#         return jsonify({'error': f'Unexpected server error: {str(e)}'}), 500


# if __name__ == '__main__':
#     app.run(debug=True, port=5000)
