# YouTube Video Downloader PRO Backend Startup Script
Write-Host "🚀 Starting YouTube Video Downloader PRO Backend..." -ForegroundColor Green
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found! Please install Python 3.8+" -ForegroundColor Red
    Write-Host "Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    pause
    exit
}

# Check if requirements are installed
Write-Host "📦 Checking dependencies..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn, yt_dlp, cv2, PIL" 2>$null
    Write-Host "✅ All dependencies are installed!" -ForegroundColor Green
} catch {
    Write-Host "❌ Some dependencies are missing!" -ForegroundColor Red
    Write-Host "Installing requirements..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

Write-Host ""
Write-Host "🌐 The backend will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "📱 Use ngrok to expose it publicly: ngrok http 8000" -ForegroundColor Cyan
Write-Host ""

# Check if port 8000 is available
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect("localhost", 8000)
    $tcpClient.Close()
    Write-Host "⚠️  Port 8000 is already in use!" -ForegroundColor Yellow
    Write-Host "Please stop any other services using port 8000" -ForegroundColor Yellow
    pause
} catch {
    Write-Host "✅ Port 8000 is available" -ForegroundColor Green
}

Write-Host ""
Write-Host "🚀 Starting backend server..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the backend
python backend_api.py
