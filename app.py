from flask import Flask, render_template, request, send_file, jsonify, after_this_request, Response
import yt_dlp
import os
import tempfile
import requests
import shutil
import threading
import time
import json
from dotenv import load_dotenv

# ==============================================================
#  GOFILE DETAILS
# ==============================================================
load_dotenv()
GOFILE_API = "https://upload.gofile.io/uploadfile"
GOFILE_TOKEN = os.getenv("GOFILE_TOKEN")  # Store your token safely

def upload_to_gofile(filepath):
    """
    Upload a file to Gofile using the Singapore endpoint first,
    then fallback to the global endpoint if needed.
    """
    if not GOFILE_TOKEN:
        print("❌ Missing GOFILE_TOKEN environment variable.")
        return None

    endpoints = [
        "https://upload-ap-sgp.gofile.io/uploadfile",  # 🌏 Asia (Singapore)
        "https://upload.gofile.io/uploadfile"          # 🌐 Global fallback
    ]

    for endpoint in endpoints:
        try:
            with open(filepath, "rb") as f:
                files = {"file": f}
                params = {"token": GOFILE_TOKEN}
                print(f"📤 Uploading to {endpoint} ...")

                r = requests.post(endpoint, files=files, data=params, timeout=90)
                r.raise_for_status()

                data = r.json()
                if data.get("status") == "ok":
                    download_link = data["data"]["downloadPage"]
                    print(f"✅ Uploaded successfully: {download_link}")
                    return download_link
                else:
                    print(f"⚠️ Gofile returned error: {data}")
        except Exception as e:
            print(f"⚠️ Upload failed at {endpoint}: {e}")

    print("❌ All Gofile endpoints failed.")
    return None

# ==============================================================
#  COOKIE HANDLING (Render + Local)
# ==============================================================
cookie_path = os.path.join(tempfile.gettempdir(), "youtube_cookies.txt")
cookie_env = os.getenv("COOKIE_FILE_CONTENTS")

if cookie_env:
    # Render or Replit: cookies from environment
    with open(cookie_path, "w", encoding="utf-8") as f:
        f.write(cookie_env)
    print(f"✅ Loaded YouTube cookies from environment into {cookie_path}")
elif os.path.exists("cookies.txt"):
    cookie_path = os.path.join(os.getcwd(), "cookies.txt")
    print("✅ Using local cookies.txt")
else:
    cookie_path = None
    print("⚠️ No cookies file found. Login-required videos may fail.")

# ==============================================================
#  FLASK SETUP
# ==============================================================
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

ALLOWED_DOMAINS = ("youtube.com", "youtu.be")
DOWNLOADS = {}  # task_id → {status, progress, filelink, error, tmpdir}


# ==============================================================
#  VALIDATION
# ==============================================================
def is_allowed_url(url: str) -> bool:
    return url.startswith(("http://", "https://")) and any(domain in url for domain in ALLOWED_DOMAINS)


# ==============================================================
#  ROUTES
# ==============================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/formats", methods=["POST"])
def get_formats():
    """Fetch available video/audio formats."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()

    if not is_allowed_url(url):
        return jsonify({"error": "Invalid or unsupported URL."}), 400

    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        if cookie_path:
            ydl_opts["cookiefile"] = cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        video_formats, audio_formats = [], []

        for f in info.get("formats", []):
            if f.get("vcodec") != "none" and f.get("acodec") != "none":
                video_formats.append({
                    "format_id": f["format_id"],
                    "ext": f["ext"],
                    "resolution": f.get("resolution") or f"{f.get('height', '?')}p",
                    "filesize": f.get("filesize")
                })
            elif f.get("vcodec") != "none":
                video_formats.append({
                    "format_id": f["format_id"],
                    "ext": f["ext"],
                    "resolution": f.get("resolution") or f"{f.get('height', '?')}p",
                    "filesize": f.get("filesize")
                })
            elif f.get("acodec") != "none":
                audio_formats.append({
                    "format_id": f["format_id"],
                    "ext": f["ext"],
                    "abr": f.get("abr", "?"),
                    "filesize": f.get("filesize")
                })

        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "video_formats": video_formats,
            "audio_formats": audio_formats
        })

    except Exception as e:
        return jsonify({"error": f"Failed to fetch formats: {str(e)}"}), 500


# ==============================================================
#  DOWNLOAD THREAD
# ==============================================================
def run_download(task_id, url, fmt, quality):
    tmpdir = tempfile.mkdtemp(prefix="ydl_")
    DOWNLOADS[task_id] = {
        "progress": 0,
        "status": "downloading",
        "tmpdir": tmpdir,
        "filelink": None,
        "error": None
    }

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            DOWNLOADS[task_id]["progress"] = int(downloaded / total * 100) if total else 0
        elif d["status"] == "finished":
            DOWNLOADS[task_id]["progress"] = 95

    ydl_opts = {
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    # Apply cookies if available
    if cookie_path and os.path.exists(cookie_path):
        ydl_opts["cookiefile"] = cookie_path

    # Handle formats
    if fmt == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192" if "128" in (quality or "") else "320",
            }]
        })
    else:
        if quality == "720p":
            ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"
        elif quality == "480p":
            ydl_opts["format"] = "bestvideo[height<=480]+bestaudio/best"
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"

    try:
        # ------------------------------
        # 1️⃣ Download
        # ------------------------------
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        # ------------------------------
        # 2️⃣ Locate the file
        # ------------------------------
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
        if not files:
            raise Exception("No output file found.")
        filepath = max(files, key=os.path.getsize)

        DOWNLOADS[task_id].update({"status": "uploading", "progress": 97})

        # ------------------------------
        # 3️⃣ Upload to Gofile
        # ------------------------------
        link = upload_to_gofile(filepath)
        if not link:
            raise Exception("Upload failed: no link returned from Gofile")

        # ------------------------------
        # 4️⃣ Mark success
        # ------------------------------
        DOWNLOADS[task_id].update({
            "filepath": filepath,
            "status": "finished",
            "progress": 100,
            "download_link": link
        })

    except Exception as e:
        DOWNLOADS[task_id].update({
            "status": "error",
            "error": str(e)
        })
        print("❌ Download error:", e)

    finally:
        # Cleanup temp folder
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

# ==============================================================
#  DOWNLOAD ENDPOINT
# ==============================================================
@app.route("/download", methods=["POST"])
def download():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid JSON payload"}), 400

        data = request.get_json(force=True)
        print("📩 Download request:", data)

        url = data.get("url")
        fmt = data.get("format")
        quality = data.get("quality")
        task_id = data.get("task_id")

        if not url:
            return jsonify({"error": "Missing URL"}), 400

        # ✅ Start download in background thread
        thread = threading.Thread(target=run_download, args=(task_id, url, fmt, quality))
        thread.start()

        return jsonify({"task_id": task_id, "status": "started"})

    except Exception as e:
        print("🔥 /download route failed:", e)
        return jsonify({"error": str(e)}), 500


# ==============================================================
#  PROGRESS ENDPOINT (SSE)
# ==============================================================
@app.route("/progress/<task_id>")
def progress(task_id):
    def generate():
        while True:
            task = DOWNLOADS.get(task_id)
            if not task:
                yield 'data: {"status": "error", "error": "Invalid task id"}\n\n'
                break

            yield f"data: {json.dumps(task)}\n\n"

            if task["status"] in ("done", "error"):
                break
            time.sleep(1)

    return Response(generate(), mimetype="text/event-stream")


# ==============================================================
#  MAIN
# ==============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))










# First Code (Only for learning) locally & online working perfectly!

# from flask import Flask, render_template, request, send_file, jsonify, after_this_request, Response
# import yt_dlp
# import os
# import tempfile
# import requests 
# import shutil
# import threading
# import time

# # ==============================================================
# #  COOKIE HANDLING (Render + Local)
# # ==============================================================
# cookie_path = os.path.join(tempfile.gettempdir(), "youtube_cookies.txt")
# cookie_env = os.getenv("COOKIE_FILE_CONTENTS")

# if cookie_env:
#     # Render will inject cookies via environment variable
#     with open(cookie_path, "w", encoding="utf-8") as f:
#         f.write(cookie_env)
#     print(f"✅ Loaded YouTube cookies from environment into {cookie_path}")
# elif os.path.exists("cookies.txt"):
#     # Local development: use cookies.txt from project root
#     cookie_path = os.path.join(os.getcwd(), "cookies.txt")
#     print("✅ Using local cookies.txt")
# else:
#     cookie_path = None
#     print("⚠️ No cookies file found. Login-required videos may fail.")

# # ==============================================================
# #  FLASK APP SETUP
# # ==============================================================
# app = Flask(__name__, static_folder='static', template_folder='templates')
# app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# ALLOWED_DOMAINS = ("youtube.com", "youtu.be")
# DOWNLOADS = {}  # {task_id: {"progress": int, "status": str, "filepath": str, "error": str}}

# # ==============================================================
# #  VALIDATION
# # ==============================================================
# def is_allowed_url(url: str) -> bool:
#     return url.startswith(('http://', 'https://')) and any(domain in url for domain in ALLOWED_DOMAINS)

# # ==============================================================
# #  ROUTES
# # ==============================================================

# @app.route('/')
# def index():
#     return render_template('index.html')


# @app.route('/formats', methods=['POST'])
# def get_formats():
#     """Fetch available video/audio formats for a given YouTube URL."""
#     data = request.get_json() or {}
#     url = data.get('url', '').strip()

#     if not is_allowed_url(url):
#         return jsonify({'error': 'Invalid or unsupported URL.'}), 400

#     try:
#         ydl_opts = {'quiet': True, 'skip_download': True}
#         if cookie_path:
#             ydl_opts['cookiefile'] = cookie_path

#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=False)

#         video_formats, audio_formats = [], []

#         for f in info.get('formats', []):
#             if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
#                 video_formats.append({
#                     'format_id': f['format_id'],
#                     'ext': f['ext'],
#                     'resolution': f.get('resolution') or f"{f.get('height', '?')}p",
#                     'filesize': f.get('filesize')
#                 })
#             elif f.get('vcodec') != 'none':
#                 video_formats.append({
#                     'format_id': f['format_id'],
#                     'ext': f['ext'],
#                     'resolution': f.get('resolution') or f"{f.get('height', '?')}p",
#                     'filesize': f.get('filesize')
#                 })
#             elif f.get('acodec') != 'none':
#                 audio_formats.append({
#                     'format_id': f['format_id'],
#                     'ext': f['ext'],
#                     'abr': f.get('abr', '?'),
#                     'filesize': f.get('filesize')
#                 })

#         return jsonify({
#             'title': info.get('title'),
#             'thumbnail': info.get('thumbnail'),
#             'video_formats': video_formats,
#             'audio_formats': audio_formats
#         })

#     except Exception as e:
#         return jsonify({'error': f'Failed to fetch formats: {str(e)}'}), 500


# # ==============================================================
# #  DOWNLOAD THREAD
# # ==============================================================
# def run_download(task_id, url, fmt, quality):
#     tmpdir = tempfile.mkdtemp(prefix="ydl_")
#     DOWNLOADS[task_id] = {"progress": 0, "status": "downloading", "tmpdir": tmpdir}

#     def progress_hook(d):
#         if d["status"] == "downloading":
#             total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
#             downloaded = d.get("downloaded_bytes", 0)
#             DOWNLOADS[task_id]["progress"] = int(downloaded / total * 100) if total else 0
#         elif d["status"] == "finished":
#             DOWNLOADS[task_id]["progress"] = 95

#     ydl_opts = {
#         "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
#         "progress_hooks": [progress_hook],
#         "quiet": True,
#         "no_warnings": True,
#         "noplaylist": True,
#     }

#     # ✅ Use cookies if available
#     if cookie_path and os.path.exists(cookie_path):
#         ydl_opts["cookiefile"] = cookie_path

#     # ✅ Format handling
#     if fmt == "mp3":
#         ydl_opts.update({
#             "format": "bestaudio/best",
#             "postprocessors": [{
#                 "key": "FFmpegExtractAudio",
#                 "preferredcodec": "mp3",
#                 "preferredquality": "192" if "128" in (quality or "") else "320",
#             }]  
#         })
#     else:
#         if quality == "720p":
#             ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best"
#         elif quality == "480p":
#             ydl_opts["format"] = "bestvideo[height<=480]+bestaudio/best"
#         else:
#             ydl_opts["format"] = "bestvideo+bestaudio/best"

#     try:
#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=True)

#         files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
#         if not files:
#             raise Exception("No output file found.")

#         filepath = max(files, key=os.path.getsize)
#         DOWNLOADS[task_id].update({"filepath": filepath, "status": "finished", "progress": 100})

#     except Exception as e:
#         DOWNLOADS[task_id].update({"status": "error", "error": str(e)})
#         print("❌ Download error:", e)


# # ==============================================================
# #  DOWNLOAD ENDPOINT
# # ==============================================================
# @app.route('/download', methods=['POST'])
# def download():
#     data = request.get_json() or {}
#     url = data.get('url', '').strip()
#     fmt = data.get('format', 'mp4')
#     quality = data.get('quality', 'best')
#     task_id = data.get('task_id')

#     if not task_id:
#         return jsonify({'error': 'Missing task id'}), 400

#     if not is_allowed_url(url):
#         return jsonify({'error': 'Invalid or unsupported URL.'}), 400

#     DOWNLOADS[task_id] = {'progress': 0, 'status': 'starting', 'filepath': None, 'error': None}
#     threading.Thread(target=run_download, args=(task_id, url, fmt, quality), daemon=True).start()

#     return jsonify({'task_id': task_id})


# # ==============================================================
# #  PROGRESS ENDPOINT
# # ==============================================================
# @app.route('/progress/<task_id>')
# def progress(task_id):
#     def generate():
#         while True:
#             task = DOWNLOADS.get(task_id)
#             if not task:
#                 yield 'data: {"status":"error","message":"Invalid task id"}\n\n'
#                 break
#             yield f'data: {{"progress": {task["progress"]}, "status": "{task["status"]}"}}\n\n'
#             if task['status'] in ('finished', 'error'):
#                 break
#             time.sleep(1)
#     return Response(generate(), mimetype='text/event-stream')


# # ==============================================================
# #  FETCH ENDPOINT
# # ==============================================================
# @app.route('/fetch/<task_id>')
# def fetch(task_id):
#     task = DOWNLOADS.get(task_id)
#     if not task:
#         return "Invalid task id", 404

#     filepath = task.get('filepath')
#     if not filepath or not os.path.exists(filepath):
#         print(f"[DEBUG] Missing file for task {task_id}: {filepath}")
#         return "Not Found", 404

#     tmpdir = task.get('tmpdir')

#     @after_this_request
#     def cleanup(response):
#         try:
#             if tmpdir and os.path.exists(tmpdir):
#                 shutil.rmtree(tmpdir)
#             DOWNLOADS.pop(task_id, None)
#         except Exception:
#             pass
#         return response

#     return send_file(filepath, as_attachment=True)


# # ==============================================================
# #  MAIN
# # ==============================================================
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
