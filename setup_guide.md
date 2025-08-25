# 🚀 Quick Setup Guide

## 📋 **Prerequisites**
- Python 3.8+ installed
- FFmpeg installed
- Node.js installed (for ngrok)

## 🔧 **Step 1: Install Dependencies**
```bash
pip install -r requirements.txt
```

## 🖥️ **Step 2: Start Backend**
```bash
python backend_api.py
```
**Keep this terminal open!** The backend runs on `http://localhost:8000`

## 🌐 **Step 3: Install & Run ngrok**
```bash
# Install ngrok
npm install -g ngrok

# Expose your backend
ngrok http 8000
```
**Copy the ngrok URL** (e.g., `https://abc123.ngrok.io`)

## ⚙️ **Step 4: Configure Frontend**

### **Option A: Vercel Environment Variables**
1. Go to Vercel Dashboard → Your Project → Settings → Environment Variables
2. Add: `BACKEND_URL` = `your-ngrok-url`
3. Redeploy

### **Option B: Browser Console**
1. Open your deployed frontend
2. Press F12 → Console
3. Run: `localStorage.setItem('backendUrl', 'your-ngrok-url')`
4. Refresh page

## ✅ **Test Your Setup**
1. Backend running on `localhost:8000` ✅
2. ngrok forwarding to your backend ✅
3. Frontend configured with ngrok URL ✅
4. Try downloading a YouTube video! 🎉

## 🔍 **Troubleshooting**
- **Backend won't start?** Check if port 8000 is free
- **ngrok not working?** Make sure backend is running first
- **Frontend can't connect?** Verify ngrok URL is correct
- **FFmpeg error?** Install FFmpeg and add to PATH

## 📱 **Your URLs**
- **Backend**: `http://localhost:8000` (local only)
- **ngrok**: `https://abc123.ngrok.io` (public)
- **Frontend**: Your Vercel URL (public)
