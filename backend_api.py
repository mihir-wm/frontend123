# MIT License
# (c) 2025 WildChild Studios — Open Source release

# YOUTUBE VIDEO DOWNLOADER PRO — Backend API
# Lightweight FastAPI backend that exposes the same functionality as the Gradio app

import os, re, shutil, zipfile, tempfile, subprocess, time, threading, queue, html, glob, json, urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import uvicorn

# Optional: requests for robust HTTP (falls back to urllib if missing)
try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    import urllib.request as _urlreq
    _HAS_REQUESTS = False

import cv2
from PIL import Image
from yt_dlp import YoutubeDL

# ====== Configuration ======
DEFAULT_FFMPEG_DIR = r"C:\ffmpeg\bin" if os.name == "nt" else ""
YTDLP_COMMON = {
    "noprogress": True,
    "quiet": True,
    "no_warnings": True,
    "retries": 1,
    "extractor_retries": 1,
    "socket_timeout": 15,
    "noplaylist": True,  # single video context
}
FALLBACK_HEIGHTS = [4320, 2160, 1440, 1080, 720]

# ====== FastAPI App ======
app = FastAPI(
    title="YouTube Video Downloader PRO API",
    description="Backend API for YouTube video downloading, audio extraction, and screenshot generation",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== Pydantic Models ======
class VideoInfoRequest(BaseModel):
    url: str

class ScreenshotsRequest(BaseModel):
    url: str
    ffmpeg_path: Optional[str] = ""
    image_res_label: str = "Best available"
    interval: float = 10.0
    mode_fast: bool = False
    save_to_folder: bool = False
    user_folder: Optional[str] = ""
    quality_preset: str = "Balanced"
    container_pref: str = "Auto (MKV)"
    use_aria2c: bool = False
    archive_enable: bool = False

class AudioRequest(BaseModel):
    url: str
    ffmpeg_path: Optional[str] = ""
    audio_mode: str = "Original (OPUS/WebM)"
    bitrate_label: str = "320 kbps"
    save_to_folder: bool = False
    user_folder: Optional[str] = ""
    use_aria2c: bool = False
    archive_enable: bool = False

class VideoRequest(BaseModel):
    url: str
    ffmpeg_path: Optional[str] = ""
    video_res_label: str = "Best available (MP4)"
    quality_preset: str = "Balanced"
    container_pref: str = "Auto (MKV)"
    save_to_folder: bool = False
    user_folder: Optional[str] = ""
    use_aria2c: bool = False
    archive_enable: bool = False

# ====== Utility Functions (same as original app.py) ======
def human_ts(seconds: float) -> str: 
    return str(timedelta(seconds=int(seconds)))

def now_tag() -> str: 
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def safe_name(s: str) -> str: 
    return re.sub(r'[\\/:*?"<>|]+', "_", (s or "")).strip()

def unique_path(dirpath: str, base: str, ext: str) -> str:
    base = safe_name(base)
    ext = ext.lstrip(".")
    cand = os.path.join(dirpath, f"{base}.{ext}")
    if not os.path.exists(cand): 
        return cand
    i = 1
    while True:
        cand = os.path.join(dirpath, f"{base}-{i:03d}.{ext}")
        if not os.path.exists(cand): 
            return cand
        i += 1

def resolve_ffmpeg_exe(override_path: Optional[str]) -> Optional[str]:
    try:
        if override_path:
            p = os.path.expanduser(override_path.strip())
            exe = p if os.path.isfile(p) else os.path.join(p, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(exe):
                if subprocess.run([exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
                    return os.path.abspath(exe)
        exe = shutil.which("ffmpeg")
        if exe and subprocess.run([exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
            return exe
    except Exception:
        pass
    return None

class _QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

def height_label(h: Optional[int]) -> str:
    mapping = {4320:"4320p (8K)", 2160:"2160p (4K)", 1440:"1440p (QHD)", 1080:"1080p (Full HD)", 720:"720p (HD)"}
    return mapping.get(h, "Best available" if h is None else f"{h}p")

def parse_height_from_label(label: str) -> Optional[int]:
    m = re.search(r"(\d{3,4})p", label or "")
    return int(m.group(1)) if m else None

# ====== URL normalization & exact-title helpers ======
_YT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

def normalize_watch_url(url: str) -> Optional[str]:
    """Turn any YouTube URL into https://www.youtube.com/watch?v=ID"""
    if not url: 
        return None
    u = url.strip()
    try:
        p = urllib.parse.urlparse(u)
        host = (p.netloc or "").lower()
        if "youtu.be" in host:
            vid = p.path.strip("/").split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}" if vid else None
        if "youtube.com" in host:
            if p.path.startswith("/shorts/"):
                vid = p.path.split("/shorts/")[1].split("/")[0]
                return f"https://www.youtube.com/watch?v={vid}"
            q = urllib.parse.parse_qs(p.query or "")
            if "v" in q and q["v"]:
                return f"https://www.youtube.com/watch?v={q['v'][0]}"
            if p.path.startswith("/watch"):
                return u
        return u
    except Exception:
        return url

def _http_get(url: str, timeout: int = 10) -> str:
    cookies = {"CONSENT": "YES+1"}  # consent bypass
    headers = {
        "User-Agent": _YT_UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        if _HAS_REQUESTS:
            r = requests.get(url, headers=headers, cookies=cookies, timeout=timeout)
            r.raise_for_status()
            return r.text
        else:
            req = _urlreq.Request(url, headers={**headers, "Cookie": "CONSENT=YES+1"})
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _http_get_json(url: str, timeout: int = 6) -> Optional[dict]:
    headers = {"User-Agent": _YT_UA, "Accept": "application/json"}
    try:
        if _HAS_REQUESTS:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        else:
            req = _urlreq.Request(url, headers=headers)
            with _urlreq.urlopen(req, timeout=timeout) as resp:
                import json as _json
                return _json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None

def oembed_title(url: str) -> Optional[str]:
    """Use YouTube oEmbed (fast, reliable) to get exact title."""
    api = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url, safe='')}&format=json"
    data = _http_get_json(api, timeout=6)
    t = (data or {}).get("title")
    t = t.strip() if isinstance(t, str) else None
    return t or None

def scrape_exact_title(url: str) -> Optional[str]:
    """Fallback scraper: ytInitialPlayerResponse -> og:title -> <title> (trim ' - YouTube')."""
    page = _http_get(url, timeout=10)
    if not page:
        return None
    m = re.search(r"ytInitialPlayerResponse\s*=\s*({.*?})\s*;\s*</script", page, re.DOTALL | re.IGNORECASE)
    if not m:
        m = re.search(r"ytInitialPlayerResponse\s*=\s*({.*?});", page, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            t = ((data.get("videoDetails") or {}).get("title") or "").strip()
            if t:
                return html.unescape(t)
        except Exception:
            pass
    m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', page, re.IGNORECASE)
    if m:
        t = html.unescape(m.group(1).strip())
        return t or None
    m = re.search(r"<title>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if m:
        t = html.unescape(m.group(1)).strip()
        t = re.sub(r"\s+-\s+YouTube$", "", t).strip()
        return t or None
    return None

def probe_resolutions_labels(url: str):
    if not url or not url.strip():
        return (["Best available (MP4)"]+[height_label(h) for h in FALLBACK_HEIGHTS],
                ["Best available"]+[height_label(h) for h in FALLBACK_HEIGHTS])
    try:
        norm = normalize_watch_url(url.strip()) or url.strip()
        with YoutubeDL({**YTDLP_COMMON, "skip_download": True, "logger": _QuietLogger()}) as ydl:
            info = ydl.extract_info(norm, download=False)
        fmts = info.get("formats") or []
        heights = sorted({f.get("height") for f in fmts if f.get("vcodec") not in ("none", None) and f.get("height")}, reverse=True)
        if not heights: 
            heights = FALLBACK_HEIGHTS
        return (["Best available (MP4)"]+[height_label(h) for h in heights],
                ["Best available"]+[height_label(h) for h in heights])
    except Exception:
        return (["Best available (MP4)"]+[height_label(h) for h in FALLBACK_HEIGHTS],
                ["Best available"]+[height_label(h) for h in FALLBACK_HEIGHTS])

# ====== API Endpoints ======
@app.get("/")
async def root():
    return {"message": "YouTube Video Downloader PRO API", "status": "running"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/video-info")
async def get_video_info(request: VideoInfoRequest):
    """Get video thumbnail, title, and available resolutions"""
    try:
        norm = normalize_watch_url(request.url.strip()) or request.url.strip()
        
        # Get title
        title = oembed_title(norm)
        if not title:
            title = scrape_exact_title(norm)
        
        # Get thumbnail and fallback title
        thumb = ""
        try:
            with YoutubeDL({**YTDLP_COMMON, "skip_download": True, "logger": _QuietLogger()}) as ydl:
                info = ydl.extract_info(norm, download=False)
            thumb = info.get("thumbnail") or ""
            if not title:
                title = (info.get("title") or "").strip()
        except Exception:
            pass
        
        # Get resolutions
        vlabels, ilabels = probe_resolutions_labels(norm)
        
        return {
            "success": True,
            "title": title,
            "thumbnail": thumb,
            "videoResolutions": vlabels,
            "imageResolutions": ilabels
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/screenshots")
async def extract_screenshots(request: ScreenshotsRequest):
    """Extract screenshots from YouTube video"""
    
    def generate_screenshots():
        try:
            # Validate inputs
            if not request.url or not request.url.strip():
                yield f"data: {json.dumps({'error': 'Please provide a valid YouTube URL'})}\n\n"
                return
            
            if request.interval <= 0:
                yield f"data: {json.dumps({'error': 'Interval must be > 0 seconds'})}\n\n"
                return
            
            # Create session directory
            session_dir = tempfile.mkdtemp(prefix="ytshots_")
            gallery_dir = os.path.join(session_dir, "screenshots")
            os.makedirs(gallery_dir, exist_ok=True)
            
            yield f"data: {json.dumps({'status': 'Starting screenshot extraction...', 'progress': 0})}\n\n"
            
            try:
                norm = normalize_watch_url(request.url.strip()) or request.url.strip()
                height = None if "Best" in (request.image_res_label or "") else parse_height_from_label(request.image_res_label)
                
                # Download video first (simplified approach)
                ydl_opts = {**YTDLP_COMMON, "format": "best[ext=mp4][acodec!=none][vcodec!=none]",
                            "outtmpl": os.path.join(session_dir, "%(title).200B.%(ext)s"), "logger": _QuietLogger()}
                
                yield f"data: {json.dumps({'status': 'Downloading video...', 'progress': 15})}\n\n"
                
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(norm, download=True)
                
                yield f"data: {json.dumps({'status': 'Video download completed, processing...', 'progress': 25})}\n\n"
                
                # Find downloaded video file
                req = info.get("requested_downloads")
                if isinstance(req, list) and req and "filepath" in req[0]:
                    video_fp = req[0]["filepath"]
                else:
                    title = safe_name(info.get("title", "video"))
                    ext = info.get("ext", "mp4")
                    video_fp = os.path.join(session_dir, f"{title}.{ext}")
                
                yield f"data: {json.dumps({'status': 'Video downloaded, extracting screenshots...', 'progress': 30})}\n\n"
                
                # Extract screenshots using OpenCV
                cap = cv2.VideoCapture(video_fp)
                if not cap.isOpened():
                    raise RuntimeError("Failed to open video with OpenCV.")
                
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                duration = frame_count / fps if frame_count > 0 else 0
                
                paths = []
                t = 0.0
                last_ok_t = -1.0
                
                while t <= duration + 1e-3:
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                    ret, frame = cap.read()
                    if not ret:
                        if last_ok_t >= 0 and (t - last_ok_t) > request.interval: 
                            break
                        t += request.interval
                        continue
                    
                    if height:
                        h, w = frame.shape[:2]
                        if h != height:
                            scale = height / max(1, h)
                            frame = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
                    
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    ts_label = human_ts(t).replace(":", "-")
                    fpath = os.path.join(gallery_dir, f"screenshot_{ts_label}.png")
                    img.save(fpath, format="PNG", optimize=True)
                    paths.append(fpath)
                    last_ok_t = t
                    t += request.interval
                    
                    progress = min(90, 30 + int(len(paths) * 60 / max(1, duration / request.interval)))
                    yield f"data: {json.dumps({'status': f'Saved {len(paths)} screenshot(s)...', 'progress': progress, 'images': paths})}\n\n"
                
                cap.release()
                
                if not paths:
                    raise RuntimeError("No screenshots were extracted.")
                
                # Create ZIP file
                yield f"data: {json.dumps({'status': 'Creating ZIP file...', 'progress': 85})}\n\n"
                
                zip_path = os.path.join(session_dir, "screenshots.zip")
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for p in paths:
                        zf.write(p, arcname=os.path.basename(p))
                
                yield f"data: {json.dumps({'status': 'ZIP file created successfully', 'progress': 90})}\n\n"
                
                # Save to user folder if requested
                if request.save_to_folder and request.user_folder:
                    dst_dir = os.path.abspath(os.path.expanduser(request.user_folder))
                    os.makedirs(dst_dir, exist_ok=True)
                    zip_dest = unique_path(dst_dir, os.path.splitext(os.path.basename(zip_path))[0], "zip")
                    shutil.copy2(zip_path, zip_dest)
                
                # Create download URL for the zip file
                zip_filename = os.path.basename(zip_path)
                download_url = f"/api/download/{zip_filename}"
                
                yield f"data: {json.dumps({'status': f'Done. Extracted {len(paths)} screenshot(s).', 'progress': 100, 'complete': True, 'zip_file': zip_path, 'download_url': download_url})}\n\n"
                
                # Keep files alive for a few minutes so they can be downloaded
                yield f"data: {json.dumps({'status': 'Files ready for download. They will be cleaned up automatically.', 'progress': 100})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Don't cleanup immediately - let files be downloaded first
                # Files will be cleaned up by the system later
                pass
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_screenshots(), media_type="text/plain")

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download a file directly"""
    try:
        # Look for the file in temp directories
        import glob
        possible_paths = []
        
        # Check common temp locations
        temp_dirs = [
            tempfile.gettempdir(),
            os.path.join(tempfile.gettempdir(), "ytshots_*"),  # Fixed prefix
            os.path.join(tempfile.gettempdir(), "ytaudio_*"),
            os.path.join(tempfile.gettempdir(), "ytvideo_*")
        ]
        
        for temp_dir in temp_dirs:
            if "*" in temp_dir:
                # Expand glob patterns
                for expanded_dir in glob.glob(temp_dir):
                    possible_paths.append(os.path.join(expanded_dir, filename))
            else:
                possible_paths.append(os.path.join(temp_dir, filename))
        
        # Find the actual file
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                break
        
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Return file as download
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio")
async def download_audio(request: AudioRequest):
    """Download audio from YouTube video"""
    
    def generate_audio():
        try:
            if not request.url or not request.url.strip():
                yield f"data: {json.dumps({'error': 'Please provide a valid YouTube URL'})}\n\n"
                return
            
            yield f"data: {json.dumps({'status': 'Starting audio download...', 'progress': 0})}\n\n"
            
            session_dir = tempfile.mkdtemp(prefix="ytaudio_")
            
            try:
                norm = normalize_watch_url(request.url.strip()) or request.url.strip()
                
                # Determine audio format settings
                if request.audio_mode == "Original (OPUS/WebM)":
                    preferredcodec, quality, final_ext, extract = "vorbis/opus", "0", None, False
                elif request.audio_mode == "MP3":
                    preferredcodec, quality, final_ext, extract = "mp3", request.bitrate_label.replace(" kbps", ""), "mp3", True
                elif request.audio_mode == "WAV":
                    preferredcodec, quality, final_ext, extract = "wav", "0", "wav", True
                else:
                    raise RuntimeError("Unsupported audio mode.")
                
                # Configure yt-dlp options
                ydl_opts = {**YTDLP_COMMON, "outtmpl": os.path.join(session_dir, "%(title).200B.%(ext)s"),
                            "merge_output_format": "mp4", "logger": _QuietLogger()}
                
                if extract:
                    ydl_opts.setdefault("postprocessors", [])
                    ydl_opts["postprocessors"].append({"key":"FFmpegExtractAudio","preferredcodec":preferredcodec,"preferredquality":quality})
                
                yield f"data: {json.dumps({'status': 'Downloading audio...', 'progress': 30})}\n\n"
                
                # Download audio
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(norm, download=True)
                
                yield f"data: {json.dumps({'status': 'Processing audio...', 'progress': 70})}\n\n"
                
                # Find produced file
                title = safe_name(info.get("title", "audio"))
                produced = None
                
                if extract:
                    for f in sorted(os.listdir(session_dir)):
                        if f.lower().startswith(title.lower()) and f.lower().endswith("." + final_ext):
                            produced = os.path.join(session_dir, f)
                else:
                    req = info.get("requested_downloads") or []
                    for r in req:
                        fp = r.get("filepath")
                        if fp and os.path.exists(fp) and fp.lower().endswith((".webm",".m4a",".mp4",".mka",".mkv",".ogg",".opus")):
                            produced = fp
                            break
                    if not produced:
                        ext = info.get("ext", "webm")
                        produced = os.path.join(session_dir, f"{title}.{ext}")
                
                if not produced:
                    raise RuntimeError("Failed to locate downloaded audio file")
                
                # Create final filename
                tag = now_tag()
                if extract:
                    base = f"{title}-{'MP3-'+quality+'kbps' if final_ext=='mp3' else 'WAV-lossless'}-{tag}"
                    download_path = unique_path(session_dir, base, final_ext)
                else:
                    ext = os.path.splitext(produced)[1].lstrip(".") or "webm"
                    base = f"{title}-ORIGINAL-{tag}"
                    download_path = unique_path(session_dir, base, ext)
                
                shutil.move(produced, download_path)
                
                # Save to user folder if requested
                if request.save_to_folder and request.user_folder:
                    dst = os.path.abspath(os.path.expanduser(request.user_folder))
                    os.makedirs(dst, exist_ok=True)
                    dest = unique_path(dst, os.path.splitext(os.path.basename(download_path))[0], download_path.split('.')[-1])
                    shutil.copy2(download_path, dest)
                
                # Create download URL for the audio file
                audio_filename = os.path.basename(download_path)
                download_url = f"/api/download/{audio_filename}"
                
                yield f"data: {json.dumps({'status': 'Audio ready!', 'progress': 100, 'complete': True, 'audio_file': download_path, 'download_url': download_url})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Cleanup temporary files
                try:
                    shutil.rmtree(session_dir)
                except:
                    pass
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_audio(), media_type="text/plain")

@app.post("/api/video")
async def download_video(request: VideoRequest):
    """Download video from YouTube"""
    
    def generate_video():
        try:
            if not request.url or not request.url.strip():
                yield f"data: {json.dumps({'error': 'Please provide a valid YouTube URL'})}\n\n"
                return
            
            yield f"data: {json.dumps({'status': 'Starting video download...', 'progress': 0})}\n\n"
            
            session_dir = tempfile.mkdtemp(prefix="ytvideo_")
            
            try:
                norm = normalize_watch_url(request.url.strip()) or request.url.strip()
                height = None if "Best" in (request.video_res_label or "") else parse_height_from_label(request.video_res_label)
                
                # Configure yt-dlp options
                mp4_compat = (request.container_pref == "MP4")
                container = "mp4" if mp4_compat else "mkv"
                
                ydl_opts = {**YTDLP_COMMON, "outtmpl": os.path.join(session_dir, "%(title).200B.%(ext)s"),
                            "merge_output_format": container, "logger": _QuietLogger()}
                
                # Set format
                v = "bestvideo"
                a = "bestaudio"
                if mp4_compat: 
                    v += "[ext=mp4]"
                    a += "[ext=m4a]"
                if height: 
                    v += f"[height<={height}]"
                ydl_opts["format"] = f"{v}+{a}/best"
                
                # Set format sorting
                if request.quality_preset == "Best quality (modern)":
                    ydl_opts["format_sort"] = ["res","fps","hdr","codec:av01:vp9.2:vp9:h264","acodec:opus:m4a","br"]
                elif request.quality_preset == "MP4 compatibility":
                    ydl_opts["format_sort"] = ["res","fps","codec:h264","acodec:m4a","br"]
                else:  # Balanced
                    ydl_opts["format_sort"] = ["res","fps","hdr","br"]
                
                yield f"data: {json.dumps({'status': 'Downloading video...', 'progress': 30})}\n\n"
                
                # Download video
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(norm, download=True)
                
                yield f"data: {json.dumps({'status': 'Processing video...', 'progress': 70})}\n\n"
                
                # Find downloaded file
                req = info.get("requested_downloads")
                if isinstance(req, list) and req and "filepath" in req[0]:
                    fp = req[0]["filepath"]
                else:
                    title = safe_name(info.get("title", "video"))
                    ext = info.get("ext", container)
                    fp = os.path.join(session_dir, f"{title}.{ext}")
                
                # Create final filename
                title = safe_name(info.get("title", "video"))
                tag = now_tag()
                suffix = f"{height_label(height)}-{tag}"
                final_path = unique_path(session_dir, f"{title}-{suffix}", container)
                shutil.move(fp, final_path)
                
                # Save to user folder if requested
                if request.save_to_folder and request.user_folder:
                    dst = os.path.abspath(os.path.expanduser(request.user_folder))
                    os.makedirs(dst, exist_ok=True)
                    ext = os.path.splitext(final_path)[1].lstrip(".") or ("mp4" if container=="mp4" else "mkv")
                    dest = unique_path(dst, os.path.splitext(os.path.basename(final_path))[0], ext)
                    shutil.copy2(final_path, dest)
                
                # Create download URL for the video file
                video_filename = os.path.basename(final_path)
                download_url = f"/api/download/{video_filename}"
                
                yield f"data: {json.dumps({'status': f'Video ready at {height_label(height)}!', 'progress': 100, 'complete': True, 'video_file': final_path, 'download_url': download_url})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Cleanup temporary files
                try:
                    shutil.rmtree(session_dir)
                except:
                    pass
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_video(), media_type="text/plain")

# ====== Main ======
if __name__ == "__main__":
    print("Starting YouTube Video Downloader PRO Backend API...")
    print("Make sure you have the required dependencies installed:")
    print("- fastapi")
    print("- uvicorn")
    print("- yt-dlp")
    print("- opencv-python")
    print("- pillow")
    print("\nTo install: pip install fastapi uvicorn yt-dlp opencv-python pillow")
    print("\nThe API will be available at: http://localhost:8000")
    print("Use ngrok to expose it publicly: ngrok http 8000")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
