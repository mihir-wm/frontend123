from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from fastapi.responses import JSONResponse
import gradio as gr

# Import Gradio app and helpers from root app.py
from app import demo, fetch_header_html, probe_resolutions_labels

app = FastAPI()

# CORS (allow Vercel site or any origin; tighten later if desired)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static frontend (HTML/CSS/JS) served at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Optional: keep Gradio available at /gradio
_fastapi_host = FastAPI()
gr_app = gr.mount_gradio_app(_fastapi_host, demo, path="/")
app.mount("/gradio", gr_app)

# Lightweight API for the static frontend
@app.post("/api/header")
def api_header(payload: dict = Body(...)):
    url = (payload or {}).get("url") or ""
    html = fetch_header_html(url)
    return JSONResponse({"html": html or ""})

@app.post("/api/resolutions")
def api_resolutions(payload: dict = Body(...)):
    url = (payload or {}).get("url") or ""
    vlabels, ilabels = probe_resolutions_labels(url)
    return JSONResponse({"video_labels": vlabels, "image_labels": ilabels})


