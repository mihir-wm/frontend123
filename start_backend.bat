@echo off
echo Starting YouTube Video Downloader PRO Backend...
echo.
echo Make sure you have installed the requirements:
echo pip install -r requirements.txt
echo.
echo The backend will be available at: http://localhost:8000
echo Use ngrok to expose it publicly: ngrok http 8000
echo.
pause
python backend_api.py
