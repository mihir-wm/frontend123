from fastapi import FastAPI
import gradio as gr

# Import the Gradio Blocks app instance `demo` from the project root `app.py`
from app import demo

# Create a FastAPI app and mount Gradio at the root path
fastapi_app = FastAPI()
app = gr.mount_gradio_app(fastapi_app, demo, path="/")


