@echo off
echo 🚀 YouTube Video Downloader PRO - Deployment Helper
echo.

echo 📁 Current project structure:
echo ├── frontend/           ← Goes to Vercel (lightweight)
echo ├── backend_api.py      ← Stays local (heavy)
echo ├── requirements.txt    ← Stays local (heavy)
echo └── vercel.json        ← Tells Vercel what to deploy
echo.

echo ✅ Frontend files are ready for Vercel deployment!
echo.

echo 🌐 To deploy:
echo 1. Push to GitHub: git add . && git commit -m "Separate frontend and backend" && git push
echo 2. Import repo in Vercel
echo 3. Vercel will automatically deploy only frontend/ folder
echo 4. Set BACKEND_URL environment variable in Vercel
echo.

echo 🔧 To run backend locally:
echo python backend_api.py
echo.

echo 📱 To expose backend publicly:
echo ngrok http 8000
echo.

pause
