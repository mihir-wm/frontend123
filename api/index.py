from fastapi import FastAPI
import gradio as gr

# Import the existing Gradio Blocks instance (`demo`) from app.py
from app import demo

# Create FastAPI app and mount Gradio at root path
_fastapi = FastAPI()
app = gr.mount_gradio_app(_fastapi, demo, path="/")


