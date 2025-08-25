# 🚀 Deployment Guide

## 📁 **Project Structure**
```
WM/
├── frontend/           # ← This goes to Vercel (lightweight)
│   ├── index.html
│   ├── styles.css
│   ├── script.js
│   └── package.json
├── backend_api.py      # ← Stays local (heavy)
├── requirements.txt    # ← Stays local (heavy)
├── vercel.json        # ← Tells Vercel to only deploy frontend/
└── .gitignore
```

## 🌐 **Deploy to Vercel**

### **Step 1: Push to GitHub**
```bash
git add .
git commit -m "Separate frontend and backend"
git push origin main
```

### **Step 2: Deploy on Vercel**
1. **Import your GitHub repo** in Vercel
2. **Vercel will automatically detect** the `vercel.json` configuration
3. **Only the `frontend/` folder** will be deployed (lightweight!)
4. **Backend files are ignored** (no more 250MB limit!)

### **Step 3: Set Environment Variable**
1. Go to **Vercel Dashboard** → Your Project → **Settings** → **Environment Variables**
2. Add: `BACKEND_URL` = `your-ngrok-url`
3. **Redeploy** your app

## ✅ **Why This Fixes the 250MB Issue**

- **Before**: Vercel tried to build everything including heavy Python dependencies
- **After**: Vercel only deploys the lightweight frontend files
- **Result**: Clean, fast deployment under 1MB!

## 🔧 **Local Development**

### **Backend (Keep Running)**
```bash
python backend_api.py
# Runs on http://localhost:8000
```

### **Frontend (Optional - for testing)**
```bash
cd frontend
npm run dev
# Runs on http://localhost:3000
```

### **ngrok (Expose Backend)**
```bash
ngrok http 8000
# Copy the public URL for Vercel
```

## 🎯 **What Gets Deployed**

✅ **Frontend Files** (to Vercel):
- `index.html` - Main page
- `styles.css` - Styling
- `script.js` - Functionality
- `package.json` - Dependencies

❌ **Backend Files** (stays local):
- `backend_api.py` - Python server
- `requirements.txt` - Python packages
- `start_backend.bat` - Windows script
- `start_backend.ps1` - PowerShell script

## 🚀 **Deploy Now!**

Your Vercel deployment should now be **under 1MB** instead of 250MB! 🎉
