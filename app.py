# MIT License
# (c) 2025 WildChild Studios — Open Source release

# YOUTUBE VIDEO DOWNLOADER PRO — Final Build
# - Exact, page-accurate YouTube title beside thumbnail:
#   * oEmbed title (primary, fastest & reliable)
#   * Normalize to watch?v=ID
#   * If oEmbed fails: fetch HTML with CONSENT cookie, parse ytInitialPlayerResponse.videoDetails.title -> og:title
#   * Final fallback: yt-dlp info["title"]
# - Default screenshots mode = "Precise (OpenCV)"
# - Live progress + cancel for images/audio/video; unique filenames; ZIP saving
# - Clean footer: adds "Powered by www.wildchildstudios.com", hides Gradio bits

import os, re, shutil, zipfile, tempfile, subprocess, time, threading, queue, html, glob, json, urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

# Optional: requests for robust HTTP (falls back to urllib if missing)
try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    import urllib.request as _urlreq
    _HAS_REQUESTS = False

import cv2
import gradio as gr
from PIL import Image
from yt_dlp import YoutubeDL

# ====== CSS (also hides Gradio’s default footer/API/Settings) ======
APP_CSS = """
:root { --brand:#ff0033; --ink:#0b1222; --muted:#687387; --edge:rgba(15,23,42,.08); }
.gradio-container { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, "Helvetica Neue", Arial; }
#appbar { display:flex; align-items:center; gap:.75rem; border:1px solid var(--edge); padding:.8rem 1.1rem; border-radius:14px;
          background:linear-gradient(180deg,#fff,#fafafa); box-shadow:0 6px 20px rgba(15,23,42,.06); margin-bottom:1rem;}
#appbar .logo{width:26px;height:19px;display:inline-block}
#appbar .ttl{font-weight:900; letter-spacing:.2px; color:var(--ink); font-size:1.35rem}
#video_header { display:flex; align-items:flex-start; gap:16px; margin:10px 0 16px; flex-wrap:wrap; }
#video_header img { width:240px; height:auto; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,.12); }
#video_header .title { font-size:1.45rem; font-weight:800; line-height:1.25; color:var(--ink); max-width:900px; word-break:break-word; }
#img_gal { height:640px !important; overflow-y:auto; border-radius:12px; }
.smallnote { color:var(--muted); font-size:.85rem }

/* Hide Gradio’s default footer/API/Settings bits */
footer, .gradio-container footer,
[data-testid="block-info"], [data-testid="api-info"],
a[href*="gradio.app"], a[href*="gradio"], a[href*="api"], a[href*="settings"] {
  display: none !important;
}

/* Custom footer */
#custom_footer { margin-top: 12px; text-align:center; color:#6b7280; font-size: .95rem; }
#custom_footer a { color:#111827; text-decoration:none; font-weight:700; }
#custom_footer a:hover { text-decoration:underline; }
"""

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

# ====== small utils ======
def human_ts(seconds: float) -> str: return str(timedelta(seconds=int(seconds)))
def now_tag() -> str: return datetime.now().strftime("%Y%m%d-%H%M%S")
def safe_name(s: str) -> str: return re.sub(r'[\\/:*?"<>|]+', "_", (s or "")).strip()
def unique_path(dirpath: str, base: str, ext: str) -> str:
    base = safe_name(base); ext = ext.lstrip("."); cand = os.path.join(dirpath, f"{base}.{ext}")
    if not os.path.exists(cand): return cand
    i = 1
    while True:
        cand = os.path.join(dirpath, f"{base}-{i:03d}.{ext}")
        if not os.path.exists(cand): return cand
        i += 1

def ffmpeg_dir_for_ytdlp(override_path: Optional[str]) -> Optional[str]:
    if not override_path: return None
    p = os.path.expanduser(override_path.strip())
    if os.path.isdir(p): return p
    if os.path.isfile(p): return os.path.dirname(p)
    return None

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
    m = re.search(r"(\d{3,4})p", label or ""); return int(m.group(1)) if m else None

# ====== URL normalization & exact-title helpers ======
_YT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

def normalize_watch_url(url: str) -> Optional[str]:
    """Turn any YouTube URL into https://www.youtube.com/watch?v=ID"""
    if not url: return None
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

# ====== Header (thumbnail + exact title) ======
def fetch_header_html(url: str) -> str:
    if not url or not url.strip():
        return ""
    norm = normalize_watch_url(url.strip()) or url.strip()

    # 1) oEmbed title (primary)
    title = oembed_title(norm)

    # 2) fallback scraper if needed
    if not title:
        title = scrape_exact_title(norm)

    thumb = ""
    try:
        with YoutubeDL({**YTDLP_COMMON, "skip_download": True, "logger": _QuietLogger()}) as ydl:
            info = ydl.extract_info(norm, download=False)
        thumb = info.get("thumbnail") or ""
        if not title:
            title = (info.get("title") or "").strip()
    except Exception:
        pass

    if not title and not thumb:
        return ""
    title = html.escape(title or "")
    thumb_tag = f"<img src='{html.escape(thumb)}' alt='thumbnail'/>" if thumb else ""
    return f"<div id='video_header'>{thumb_tag}<div class='title'>{title}</div></div>"

# ====== Resolution probe ======
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
        if not heights: heights = FALLBACK_HEIGHTS
        return (["Best available (MP4)"]+[height_label(h) for h in heights],
                ["Best available"]+[height_label(h) for h in heights])
    except Exception:
        return (["Best available (MP4)"]+[height_label(h) for h in FALLBACK_HEIGHTS],
                ["Best available"]+[height_label(h) for h in FALLBACK_HEIGHTS])

# ====== yt-dlp helpers (progress + cancel) ======
class Cancelled(Exception): pass

def _yt_dlp_with_progress(url: str, ydl_opts: dict, progress_state: dict, cancel_event: Optional[threading.Event] = None):
    def hook(d):
        if cancel_event is not None and cancel_event.is_set(): raise Cancelled("Cancelled by user")
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                if total > 0: progress_state["pct"] = max(0, min(100, int(done * 100 / total)))
            elif d.get("status") == "finished":
                progress_state["pct"] = 100
        except Exception: pass
    ydl_opts = {**ydl_opts, "progress_hooks": [hook]}
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=True)

def build_format_string(height: Optional[int], mp4_compat: bool) -> str:
    v = "bestvideo"; a = "bestaudio"
    if mp4_compat: v += "[ext=mp4]"; a += "[ext=m4a]"
    if height: v += f"[height<={height}]"
    return f"{v}+{a}/best"

def build_format_sort(preset: str) -> List[str]:
    return (["res","fps","hdr","codec:av01:vp9.2:vp9:h264","acodec:opus:m4a","br"] if preset=="Best quality (modern)"
            else ["res","fps","codec:h264","acodec:m4a","br"] if preset=="MP4 compatibility"
            else ["res","fps","hdr","br"])

def common_ydl_opts(out_dir: str, ffmpeg_path: Optional[str], ext_dl: bool,
                    add_meta: bool, embed_thumb: bool, write_subs: bool, embed_subs: bool,
                    split_chapters: bool, write_infojson: bool, container: str, archive_path: Optional[str]) -> Dict:
    opts = {**YTDLP_COMMON, "outtmpl": os.path.join(out_dir, "%(title).200B.%(ext)s"),
            "merge_output_format": container, "logger": _QuietLogger()}
    loc = ffmpeg_dir_for_ytdlp(ffmpeg_path)
    if loc: opts["ffmpeg_location"] = loc
    if ext_dl: opts["external_downloader"] = "aria2c"
    pp=[]
    if add_meta: pp.append({"key":"FFmpegMetadata"})
    if embed_thumb: pp.append({"key":"EmbedThumbnail"})
    if write_subs:  opts["writesubtitles"]=True; opts["subtitlesformat"]="srt"
    if embed_subs:  opts["embedsubtitles"]=True
    if split_chapters: opts["split_chapters"]=True
    if write_infojson: opts["writeinfojson"]=True
    if archive_path: opts["download_archive"]=archive_path
    if pp: opts["postprocessors"]=pp
    return opts

def _download_video_blocking(url: str, work_dir: str, ffmpeg_path: Optional[str],
                             height: Optional[int], progress_state: dict, cancel_event: Optional[threading.Event],
                             quality_preset: str, container_pref: str, use_aria2c: bool,
                             add_meta: bool, embed_thumb: bool, write_subs: bool, embed_subs: bool,
                             split_chapters: bool, write_infojson: bool, archive_path: Optional[str]) -> str:
    if not resolve_ffmpeg_exe(ffmpeg_path): raise RuntimeError("FFmpeg not found. Install it at C:\\ffmpeg\\bin.")
    mp4_compat = (container_pref == "MP4"); container = "mp4" if mp4_compat else "mkv"
    ydl_opts = common_ydl_opts(work_dir, ffmpeg_path, use_aria2c, add_meta, embed_thumb, write_subs,
                               embed_subs, split_chapters, write_infojson, container, archive_path)
    ydl_opts["format"] = build_format_string(height, mp4_compat)
    ydl_opts["format_sort"] = build_format_sort(quality_preset)
    info = _yt_dlp_with_progress(url, ydl_opts, progress_state, cancel_event)
    title = safe_name(info.get("title", "video"))
    req = info.get("requested_downloads")
    if isinstance(req, list) and req and "filepath" in req[0]: fp = req[0]["filepath"]
    else:
        ext = info.get("ext", container); fp = os.path.join(work_dir, f"{title}.{ext}")
    tag = now_tag(); suffix = f"{height_label(height)}-{tag}"
    final_path = unique_path(work_dir, f"{title}-{suffix}", container)
    shutil.move(fp, final_path)
    return final_path

def _download_audio_blocking(url: str, work_dir: str, ffmpeg_path: Optional[str],
                             audio_mode: str, bitrate_kbps: str, progress_state: dict,
                             cancel_event: Optional[threading.Event], use_aria2c: bool,
                             add_meta: bool, embed_thumb: bool, write_infojson: bool, archive_path: Optional[str]) -> Tuple[str, str]:
    if not resolve_ffmpeg_exe(ffmpeg_path): raise RuntimeError("FFmpeg not found. Install it at C:\\ffmpeg\\bin.")
    if audio_mode == "Original (OPUS/WebM)":
        preferredcodec, quality, final_ext, extract = "vorbis/opus", "0", None, False
    elif audio_mode == "MP3":
        preferredcodec, quality, final_ext, extract = "mp3", bitrate_kbps, "mp3", True
    elif audio_mode == "WAV":
        preferredcodec, quality, final_ext, extract = "wav", "0", "wav", True
    else:
        raise RuntimeError("Unsupported audio mode.")
    ydl_opts = common_ydl_opts(work_dir, ffmpeg_path, use_aria2c, add_meta, embed_thumb, False, False, False, write_infojson, "mp4", archive_path)
    ydl_opts["format"] = "bestaudio/best"
    if extract:
        ydl_opts.setdefault("postprocessors", [])
        ydl_opts["postprocessors"].append({"key":"FFmpegExtractAudio","preferredcodec":preferredcodec,"preferredquality":quality})
    info = _yt_dlp_with_progress(url, ydl_opts, progress_state, cancel_event)
    title = safe_name(info.get("title", "audio"))
    produced = None
    if extract:
        for f in sorted(os.listdir(work_dir)):
            if f.lower().startswith(title.lower()) and f.lower().endswith("." + final_ext):
                produced = os.path.join(work_dir, f)
    else:
        req = info.get("requested_downloads") or []
        for r in req:
            fp = r.get("filepath")
            if fp and os.path.exists(fp) and fp.lower().endswith((".webm",".m4a",".mp4",".mka",".mkv",".ogg",".opus")):
                produced = fp; break
        if not produced:
            ext = info.get("ext", "webm"); produced = os.path.join(work_dir, f"{title}.{ext}")
    tag = now_tag()
    if extract:
        base = f"{title}-{'MP3-'+bitrate_kbps+'kbps' if final_ext=='mp3' else 'WAV-lossless'}-{tag}"
        download_path = unique_path(work_dir, base, final_ext)
    else:
        ext = os.path.splitext(produced)[1].lstrip(".") or "webm"
        base = f"{title}-ORIGINAL-{tag}"
        download_path = unique_path(work_dir, base, ext)
    shutil.move(produced, download_path)
    preview_path = download_path
    ffmpeg_exe = resolve_ffmpeg_exe(ffmpeg_path)
    if not download_path.lower().endswith(".wav") and ffmpeg_exe:
        preview_path = unique_path(work_dir, f"{os.path.splitext(os.path.basename(download_path))[0]}-preview", "wav")
        subprocess.run([ffmpeg_exe,"-y","-i",download_path,"-ar","44100","-ac","2","-acodec","pcm_s16le",preview_path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return preview_path, download_path

# ====== Instant screenshots via FFmpeg reading the stream URL ======
def pick_stream_url(url: str, target_height: Optional[int]) -> Tuple[str, Dict[str,str]]:
    with YoutubeDL({**YTDLP_COMMON, "skip_download": True, "logger": _QuietLogger()}) as ydl:
        info = ydl.extract_info(url.strip(), download=False)
    fmts = [f for f in (info.get("formats") or []) if f.get("vcodec") not in ("none", None)]
    def score(f):
        h = f.get("height") or 0
        penal = 0 if (f.get("protocol") in ("https","http") and f.get("ext") in ("mp4","webm")) else 1
        return (-(h if (not target_height or h <= target_height) else 10**6), penal)
    fmts_sorted = sorted(fmts, key=score)
    if not fmts_sorted: raise RuntimeError("No streamable video formats found.")
    chosen = fmts_sorted[0]
    stream_url = chosen.get("url"); headers = info.get("http_headers") or {}
    if not stream_url: raise RuntimeError("Failed to resolve video stream URL.")
    return stream_url, headers

def ffmpeg_extract_frames_from_url(stream_url: str, headers: Dict[str,str],
                                   every_sec: float, out_dir: str, target_height: Optional[int],
                                   ffmpeg_exe: str, cancel_event: threading.Event):
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "shot_%05d.png")
    vf = [f"fps=1/{max(0.1, every_sec)}"]
    if target_height: vf.append(f"scale=-1:{target_height}:flags=bicubic")
    vf_str = ",".join(vf)
    hdr = "".join([f"{k}: {v}\r\n" for k, v in headers.items()]) if headers else None
    cmd = [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y"]
    if hdr: cmd += ["-headers", hdr]
    cmd += ["-i", stream_url, "-vf", vf_str, pattern]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    last_count = 0
    try:
        while True:
            if cancel_event.is_set():
                proc.terminate()
                try: proc.wait(timeout=2)
                except Exception: proc.kill()
                raise Cancelled("Cancelled by user")
            time.sleep(0.3)
            files = sorted(glob.glob(os.path.join(out_dir, "shot_*.png")))
            if len(files) != last_count:
                last_count = len(files)
                yield files, f"Saved {last_count} screenshot(s)…"
            if proc.poll() is not None:
                files = sorted(glob.glob(os.path.join(out_dir, "shot_*.png")))
                if len(files) != last_count:
                    yield files, f"Saved {len(files)} screenshot(s)…"
                break
    finally:
        if proc.poll() is None:
            try: proc.terminate()
            except Exception: pass

# Fallback local extraction (OpenCV)
def opencv_extract_stream(video_path: str, interval_sec: float, out_dir: str,
                          target_height: Optional[int], cancel_event: threading.Event):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened(): raise RuntimeError("Failed to open video with OpenCV.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if frame_count > 0 else 0
    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []
    t = 0.0; last_ok_t = -1.0
    while t <= duration + 1e-3:
        if cancel_event.is_set(): raise Cancelled("Cancelled by user")
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ret, frame = cap.read()
        if not ret:
            if last_ok_t >= 0 and (t - last_ok_t) > interval_sec: break
            t += interval_sec; continue
        if target_height:
            h, w = frame.shape[:2]
            if h != target_height:
                scale = target_height / max(1, h)
                frame = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        ts_label = human_ts(t).replace(":", "-")
        fpath = os.path.join(out_dir, f"screenshot_{ts_label}.png")
        img.save(fpath, format="PNG", optimize=True)
        paths.append(fpath)
        last_ok_t = t
        t += interval_sec
        yield paths, f"Saved {len(paths)} screenshot(s)…"
    cap.release()
    if not paths: raise RuntimeError("No screenshots were extracted.")
    yield paths, f"Done. Extracted {len(paths)} screenshot(s)."

def zip_paths(filepaths: List[str], zip_path: str) -> str:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in filepaths: zf.write(p, arcname=os.path.basename(p))
    return zip_path

# ====== Pipelines ======
def run_screenshots_stream(url: str, ffmpeg_path: str, image_res_label: str, interval: float,
                           mode_fast: bool, save_to_folder: bool, user_folder: str,
                           quality_preset: str, container_pref: str, use_aria2c: bool,
                           img_cancel_state):
    if not url or not url.strip():
        yield gr.update(value=0, visible=False), None, None, "Please paste a valid YouTube link.", None; return
    if interval is None or interval <= 0:
        yield gr.update(value=0, visible=False), None, None, "Interval must be > 0 sec.", None; return

    cancel_ev = threading.Event()
    session_dir = tempfile.mkdtemp(prefix="ytshots_")
    gallery_dir = os.path.join(session_dir, "screenshots"); os.makedirs(gallery_dir, exist_ok=True)
    yield gr.update(value=0, visible=True), [], None, "Starting… 0%", cancel_ev

    try:
        height = None if "Best" in (image_res_label or "") else parse_height_from_label(image_res_label)
        ffmpeg_exe = resolve_ffmpeg_exe(ffmpeg_path or None)
        norm = normalize_watch_url(url.strip()) or url.strip()

        if mode_fast and ffmpeg_exe:
            try:
                stream_url, headers = pick_stream_url(norm, height)
                gen = ffmpeg_extract_frames_from_url(stream_url, headers, float(interval), gallery_dir, height, ffmpeg_exe, cancel_ev)
                for paths, msg in gen:
                    pct = min(100, max(1, int(len(paths) * 4)))
                    yield gr.update(value=pct, visible=True), paths, None, msg, cancel_ev
            except Exception as e:
                # Fallback: progressive MP4 + OpenCV
                yield gr.update(value=0, visible=True), [], None, f"Stream extraction failed ({e}); falling back…", cancel_ev
                ydl_opts = {**YTDLP_COMMON, "format": "best[ext=mp4][acodec!=none][vcodec!=none]",
                            "outtmpl": os.path.join(session_dir, "%(title).200B.%(ext)s"), "logger": _QuietLogger()}
                progress_state = {"pct": 0}
                info = _yt_dlp_with_progress(norm, ydl_opts, progress_state, cancel_ev)
                req = info.get("requested_downloads")
                if isinstance(req, list) and req and "filepath" in req[0]:
                    video_fp = req[0]["filepath"]
                else:
                    title = safe_name(info.get("title","video")); ext = info.get("ext","mp4")
                    video_fp = os.path.join(session_dir, f"{title}.{ext}")
                gen2 = opencv_extract_stream(video_fp, float(interval), gallery_dir, height, cancel_ev)
                for paths, msg in gen2:
                    pct = min(100, max(1, int(len(paths) * 4)))
                    yield gr.update(value=pct, visible=True), paths, None, msg, cancel_ev
        else:
            # Default Precise (OpenCV): download progressive MP4 first
            ydl_opts = {**YTDLP_COMMON, "format": "best[ext=mp4][acodec!=none][vcodec!=none]",
                        "outtmpl": os.path.join(session_dir, "%(title).200B.%(ext)s"), "logger": _QuietLogger()}
            progress_state = {"pct": 0}
            info = _yt_dlp_with_progress(norm, ydl_opts, progress_state, cancel_ev)
            req = info.get("requested_downloads")
            if isinstance(req, list) and req and "filepath" in req[0]:
                video_fp = req[0]["filepath"]
            else:
                title = safe_name(info.get("title","video")); ext = info.get("ext","mp4")
                video_fp = os.path.join(session_dir, f"{title}.{ext}")
            gen = opencv_extract_stream(video_fp, float(interval), gallery_dir, height, cancel_ev)
            for paths, msg in gen:
                pct = min(100, max(1, int(len(paths) * 4)))
                yield gr.update(value=pct, visible=True), paths, None, msg, cancel_ev

        files = sorted(glob.glob(os.path.join(gallery_dir, "shot_*.png")))+sorted(glob.glob(os.path.join(gallery_dir, "screenshot_*.png")))
        zip_path = os.path.join(session_dir, "screenshots.zip")
        zip_paths(files, zip_path)
        if save_to_folder and user_folder:
            dst_dir = os.path.abspath(os.path.expanduser(user_folder)); os.makedirs(dst_dir, exist_ok=True)
            zip_dest = unique_path(dst_dir, os.path.splitext(os.path.basename(zip_path))[0], "zip"); shutil.copy2(zip_path, zip_dest)
        yield gr.update(value=100, visible=False), files, zip_path, f"Done. Extracted {len(files)} screenshot(s).", cancel_ev

    except Cancelled:
        yield gr.update(value=0, visible=False), None, None, "Cancelled.", cancel_ev
    except Exception as e:
        yield gr.update(value=0, visible=False), None, None, f"Error: {e}", cancel_ev

def run_get_full_audio_stream(url: str, ffmpeg_path: str, audio_mode: str, bitrate_label: str,
                              save_to_folder: bool, user_folder: str, audio_list: List[str],
                              use_aria2c: bool, add_meta: bool, embed_thumb: bool,
                              write_infojson: bool, archive_enable: bool, aud_cancel_state):
    if not url or not url.strip():
        yield gr.update(value=0, visible=False), None, None, audio_list, "Please paste a valid YouTube link.", audio_list, None; return
    cancel_ev = threading.Event()
    session_dir = tempfile.mkdtemp(prefix="ytaudio_")
    progress_state = {"pct": 0}
    result_q, err_q = queue.Queue(), queue.Queue()
    archive_path = None
    if archive_enable:
        if save_to_folder and user_folder: archive_path = os.path.join(os.path.abspath(os.path.expanduser(user_folder)), "download_archive.txt")
        else: archive_path = os.path.join(os.getcwd(), "download_archive.txt")
    def worker():
        try:
            bitrate = bitrate_label.replace(" kbps","") if audio_mode=="MP3" else "0"
            preview_fp, download_fp = _download_audio_blocking(normalize_watch_url(url.strip()) or url.strip(), session_dir, ffmpeg_path or None, audio_mode, bitrate,
                                                               progress_state, cancel_ev, use_aria2c, add_meta, embed_thumb, write_infojson, archive_path)
            result_q.put((preview_fp, download_fp))
        except Cancelled as e: err_q.put(("CANCELLED", str(e)))
        except Exception as e: err_q.put(("ERROR", str(e)))
    threading.Thread(target=worker, daemon=True).start()
    yield gr.update(value=0, visible=True), None, None, audio_list, "Starting… 0%", audio_list, cancel_ev
    last_pct = -1
    while err_q.empty() and result_q.empty():
        if cancel_ev.is_set(): yield gr.update(value=last_pct if last_pct>=0 else 0, visible=True), None, None, audio_list, "Cancelling…", audio_list, cancel_ev
        pct = progress_state.get("pct", 0)
        if pct != last_pct:
            yield gr.update(value=pct, visible=True), None, None, audio_list, f"Downloading… {pct}%", audio_list, cancel_ev
            last_pct = pct
        time.sleep(0.2)
    if not err_q.empty():
        kind, msg = err_q.get()
        if kind == "CANCELLED": yield gr.update(value=last_pct if last_pct>=0 else 0, visible=False), None, None, audio_list, "Cancelled.", audio_list, cancel_ev; return
        else: yield gr.update(value=last_pct if last_pct>=0 else 0, visible=False), None, None, audio_list, f"Error: {msg}", audio_list, cancel_ev; return
    preview_fp, download_fp = result_q.get()
    msg = f"Audio ready ({os.path.splitext(download_fp)[1].lstrip('.').upper()})."
    if save_to_folder and user_folder:
        dst = os.path.abspath(os.path.expanduser(user_folder)); os.makedirs(dst, exist_ok=True)
        dest = unique_path(dst, os.path.splitext(os.path.basename(download_fp))[0], download_fp.split('.')[-1]); shutil.copy2(download_fp, dest)
        msg += f" Saved to: {dst}"
    audio_list = list(audio_list or []); audio_list.append(download_fp)
    yield gr.update(value=100, visible=False), preview_fp, download_fp, audio_list, msg+" File ready.", audio_list, cancel_ev

def run_get_full_video_stream(url: str, ffmpeg_path: str, video_res_label: str,
                              quality_preset: str, container_pref: str,
                              save_to_folder: bool, user_folder: str, video_list: List[str],
                              use_aria2c: bool,
                              add_meta: bool, embed_thumb: bool, write_subs: bool, embed_subs: bool,
                              split_chapters: bool, write_infojson: bool, archive_enable: bool, vid_cancel_state):
    if not url or not url.strip():
        yield gr.update(value=0, visible=False), None, None, video_list, "Please paste a valid YouTube link.", video_list, None; return
    cancel_ev = threading.Event()
    session_dir = tempfile.mkdtemp(prefix="ytvideo_")
    progress_state = {"pct": 0}
    result_q, err_q = queue.Queue(), queue.Queue()
    archive_path = None
    if archive_enable:
        if save_to_folder and user_folder: archive_path = os.path.join(os.path.abspath(os.path.expanduser(user_folder)), "download_archive.txt")
        else: archive_path = os.path.join(os.getcwd(), "download_archive.txt")
    def worker():
        try:
            height = None if "Best" in (video_res_label or "") else parse_height_from_label(video_res_label)
            video_fp = _download_video_blocking(normalize_watch_url(url.strip()) or url.strip(), session_dir, ffmpeg_path or None, height, progress_state, cancel_ev,
                                                quality_preset, container_pref, use_aria2c, add_meta, embed_thumb, write_subs, embed_subs,
                                                split_chapters, write_infojson, archive_path)
            result_q.put((video_fp, height))
        except Cancelled as e: err_q.put(("CANCELLED", str(e)))
        except Exception as e: err_q.put(("ERROR", str(e)))
    threading.Thread(target=worker, daemon=True).start()
    yield gr.update(value=0, visible=True), None, None, video_list, "Starting… 0%", video_list, cancel_ev
    last_pct = -1
    while err_q.empty() and result_q.empty():
        if cancel_ev.is_set(): yield gr.update(value=last_pct if last_pct>=0 else 0, visible=True), None, None, video_list, "Cancelling…", video_list, cancel_ev
        pct = progress_state.get("pct", 0)
        if pct != last_pct:
            yield gr.update(value=pct, visible=True), None, None, video_list, f"Downloading… {pct}%", video_list, cancel_ev
            last_pct = pct
        time.sleep(0.2)
    if not err_q.empty():
        kind, msg = err_q.get()
        if kind == "CANCELLED": yield gr.update(value=last_pct if last_pct>=0 else 0, visible=False), None, None, video_list, "Cancelled.", video_list, cancel_ev; return
        else: yield gr.update(value=last_pct if last_pct>=0 else 0, visible=False), None, None, video_list, f"Error: {msg}", video_list, cancel_ev; return
    video_fp, height = result_q.get()
    msg = f"Video ready at {height_label(height)}."
    if save_to_folder and user_folder:
        dst = os.path.abspath(os.path.expanduser(user_folder)); os.makedirs(dst, exist_ok=True)
        ext = os.path.splitext(video_fp)[1].lstrip(".") or ("mp4" if container_pref=="MP4" else "mkv")
        dest = unique_path(dst, os.path.splitext(os.path.basename(video_fp))[0], ext); shutil.copy2(video_fp, dest)
        msg += f" Saved to: {dst}"
    video_list = list(video_list or []); video_list.append(video_fp)
    yield gr.update(value=100, visible=False), video_fp, video_fp, video_list, msg+" File ready.", video_list, cancel_ev

# ====== Cancel handler ======
def cancel_generic(cancel_ev):
    try:
        if cancel_ev: cancel_ev.set()
    except Exception: pass
    return gr.update(visible=False), "Cancelling…"

# ====== UI ======
with gr.Blocks(title="YouTube Video Downloader PRO", css=APP_CSS) as demo:
    gr.HTML("""<div id="appbar">
      <svg class="logo" viewBox="0 0 24 17" xmlns="http://www.w3.org/2000/svg"><path fill="#FF0033" d="M23.5 2.5a4 4 0 0 0-2.8-2.8C18.6-.9 12-.9 12-.9s-6.6 0-8.7.6A4 4 0 0 0 .5 2.5 41.2 41.2 0 0 0 0 8c0 1.9.2 3.8.5 5.5a4 4 0 0 0 2.8 2.8c2.1.6 8.7.6 8.7.6s6.6 0 8.7-.6a4 4 0 0 0 2.8-2.8A41.2 41.2 0 0 0 24 8c0-1.9-.2-3.8-.5-5.5Z"/><path fill="#fff" d="M9.6 12.1V3.9L16 8l-6.4 4.1z"/></svg>
      <div class="ttl">YOUTUBE VIDEO DOWNLOADER PRO</div></div>""")

    with gr.Row():
        url_in = gr.Textbox(label="YouTube Video URL", placeholder="https://www.youtube.com/watch?v=...", scale=3)
        ffmpeg_in = gr.Textbox(label="FFmpeg path (pre-filled)", value=DEFAULT_FFMPEG_DIR, scale=2)

    header_html = gr.HTML(value="")  # thumbnail + exact title

    with gr.Row():
        save_chk = gr.Checkbox(value=False, label="Also save outputs to this folder")
        folder_in = gr.Textbox(label="Folder path", placeholder=r"C:\Users\You\Downloads\yt_outputs", scale=3)

    with gr.Row():
        with gr.Column():
            gr.Markdown("#### Global quality & performance", elem_classes=["smallnote"])
            with gr.Row():
                quality_preset = gr.Dropdown(choices=["Balanced","Best quality (modern)","MP4 compatibility"], value="Balanced", label="Quality preset")
                container_pref = gr.Dropdown(choices=["Auto (MKV)","MP4"], value="Auto (MKV)", label="Container")
            use_aria2c = gr.Checkbox(value=False, label="Use aria2c if available (faster for some)")
            archive_enable = gr.Checkbox(value=False, label="Skip already downloaded (archive)")

    audio_files_state = gr.State([]); video_files_state = gr.State([])
    img_cancel_state = gr.State(None); aud_cancel_state = gr.State(None); vid_cancel_state = gr.State(None)

    with gr.Row():
        with gr.Column():
            gr.Markdown("#### Images (Screenshots)")
            with gr.Row():
                image_res_dd = gr.Dropdown(choices=["Best available"], value="Best available", label="Image Resolution")
                img_mode = gr.Radio(choices=["Fast (FFmpeg)","Precise (OpenCV)"], value="Precise (OpenCV)", label="Extraction mode")
            interval_in = gr.Number(value=10, precision=1, label="Interval (seconds)")
            with gr.Row():
                run_btn = gr.Button("Get Screenshots", variant="primary")
                cancel_img_btn = gr.Button("Cancel")
            images_progress = gr.Slider(minimum=0, maximum=100, value=0, step=1, interactive=False, label="Progress", visible=False)
            images_gallery = gr.Gallery(label="Thumbnails", show_label=True, columns=2, height=640, preview=True, elem_id="img_gal")
            zip_out = gr.File(label="Download all screenshots as ZIP")
            status_img = gr.Markdown()

        with gr.Column():
            gr.Markdown("#### Audio")
            with gr.Row():
                audio_mode = gr.Dropdown(choices=["Original (OPUS/WebM)","MP3","WAV"], value="Original (OPUS/WebM)", label="Format")
                bitrate_dd = gr.Dropdown(choices=["320 kbps","256 kbps","192 kbps","128 kbps"], value="320 kbps", label="MP3 Bitrate")
            with gr.Row():
                audio_btn = gr.Button("Get full Audio"); cancel_audio_btn = gr.Button("Cancel")
            audio_progress = gr.Slider(minimum=0, maximum=100, value=0, step=1, interactive=False, label="Download progress", visible=False)
            audio_player = gr.Audio(label="Preview Audio", interactive=False, type="filepath")
            audio_file = gr.File(label="Downloaded Audio File")
            audio_files = gr.Files(label="All Downloaded Audio (session)")
            status_audio = gr.Markdown()

        with gr.Column():
            gr.Markdown("#### Video")
            video_res_dd = gr.Dropdown(choices=["Best available (MP4)"]+[height_label(h) for h in FALLBACK_HEIGHTS], value="Best available (MP4)", label="Resolution")
            with gr.Row():
                video_btn = gr.Button("Get full Video"); cancel_video_btn = gr.Button("Cancel")
            video_progress = gr.Slider(minimum=0, maximum=100, value=0, step=1, interactive=False, label="Download progress", visible=False)
            video_player = gr.Video(label="Preview Video")
            video_file = gr.File(label="Downloaded Video File")
            video_files = gr.Files(label="All Downloaded Video (session)")
            status_video = gr.Markdown()

    # URL change → header + dynamic resolution lists
    def on_url_change(url: str):
        norm = normalize_watch_url(url or "")
        head = fetch_header_html(norm or url)
        vlabels, ilabels = probe_resolutions_labels(norm or url)
        return head, gr.update(choices=vlabels, value=vlabels[0]), gr.update(choices=ilabels, value=ilabels[0])
    url_in.change(fn=on_url_change, inputs=[url_in], outputs=[header_html, video_res_dd, image_res_dd])

    # Generators
    def call_images(url, ffmpeg, res, interval, mode_label, save_to, folder, q_preset, cont_pref, aria, cancel_state):
        yield from run_screenshots_stream(url, ffmpeg, res, float(interval), mode_label=="Fast (FFmpeg)",
                                          save_to, folder, q_preset, ("MP4" if cont_pref=="MP4" else "Auto (MKV)"),
                                          bool(aria), cancel_state)
    run_btn.click(fn=call_images,
                  inputs=[url_in, ffmpeg_in, image_res_dd, interval_in, img_mode, save_chk, folder_in, quality_preset, container_pref, use_aria2c, img_cancel_state],
                  outputs=[images_progress, images_gallery, zip_out, status_img, img_cancel_state])
    cancel_img_btn.click(fn=cancel_generic, inputs=[img_cancel_state], outputs=[images_progress, status_img])

    def call_audio(url, ffmpeg, fmt, br, save_to, folder, audio_state, aria, archive, cancel):
        yield from run_get_full_audio_stream(url, ffmpeg, fmt, br, save_to, folder, audio_state, bool(aria),
                                             True, False, False, bool(archive), cancel)
    audio_btn.click(fn=call_audio,
                    inputs=[url_in, ffmpeg_in, audio_mode, bitrate_dd, save_chk, folder_in, audio_files_state, use_aria2c, archive_enable, aud_cancel_state],
                    outputs=[audio_progress, audio_player, audio_file, audio_files, status_audio, audio_files_state, aud_cancel_state])
    cancel_audio_btn.click(fn=cancel_generic, inputs=[aud_cancel_state], outputs=[audio_progress, status_audio])

    def call_video(url, ffmpeg, vres, q_preset, cont_pref, save_to, folder, video_state, aria, archive, cancel):
        yield from run_get_full_video_stream(url, ffmpeg, vres, q_preset, (cont_pref if cont_pref in ["MP4","Auto (MKV)"] else "Auto (MKV)"),
                                             save_to, folder, video_state, bool(aria),
                                             True, False, False, False, False, False, bool(archive), cancel)
    video_btn.click(fn=call_video,
                    inputs=[url_in, ffmpeg_in, video_res_dd, quality_preset, container_pref, save_chk, folder_in, video_files_state, use_aria2c, archive_enable, vid_cancel_state],
                    outputs=[video_progress, video_player, video_file, video_files, status_video, video_files_state, vid_cancel_state])

    gr.HTML('<div id="custom_footer">Powered by <a href="https://www.wildchildstudios.com" target="_blank">www.wildchildstudios.com</a></div>')

# Queue & launch (handle older Gradio)
demo.queue()
if __name__ == "__main__":
    try:
        demo.launch(show_api=False)
    except TypeError:
        demo.launch()
