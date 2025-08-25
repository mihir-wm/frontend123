// YouTube Video Downloader PRO Frontend
class YouTubeDownloader {
    constructor() {
        this.backendUrl = this.getBackendUrl();
        this.currentCancelEvent = null;
        this.init();
    }

    getBackendUrl() {
        // Try to get from environment variable first, then fallback to localhost
        if (typeof process !== 'undefined' && process.env.BACKEND_URL) {
            return process.env.BACKEND_URL;
        }
        
        // For browser environment, check localStorage or use default
        const savedUrl = localStorage.getItem('backendUrl');
        if (savedUrl) {
            return savedUrl;
        }
        
        // Check if we're on Vercel and need to set backend URL
        if (window.location.hostname.includes('vercel.app')) {
            console.warn('Running on Vercel but no backend URL set. Please set BACKEND_URL environment variable.');
            // You can set this manually in browser console:
            // localStorage.setItem('backendUrl', 'https://your-ngrok-url.ngrok.io')
        }
        
        // Default to localhost with ngrok (you can change this)
        return 'http://localhost:8000';
    }

    init() {
        this.setupEventListeners();
        this.setupTabs();
        this.loadSettings();
    }

    setupEventListeners() {
        // URL input change
        document.getElementById('youtube-url').addEventListener('input', (e) => {
            this.onUrlChange(e.target.value);
        });

        // Screenshots
        document.getElementById('screenshots-btn').addEventListener('click', () => {
            this.startScreenshots();
        });
        document.getElementById('cancel-screenshots-btn').addEventListener('click', () => {
            this.cancelOperation('screenshots');
        });

        // Audio
        document.getElementById('audio-btn').addEventListener('click', () => {
            this.startAudioDownload();
        });
        document.getElementById('cancel-audio-btn').addEventListener('click', () => {
            this.cancelOperation('audio');
        });

        // Video
        document.getElementById('video-btn').addEventListener('click', () => {
            this.startVideoDownload();
        });
        document.getElementById('cancel-video-btn').addEventListener('click', () => {
            this.cancelOperation('video');
        });

        // Settings persistence
        this.setupSettingsPersistence();
    }

    setupTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.dataset.tab;
                
                // Update active states
                tabBtns.forEach(b => b.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));
                
                btn.classList.add('active');
                document.getElementById(targetTab).classList.add('active');
            });
        });
    }

    setupSettingsPersistence() {
        const inputs = document.querySelectorAll('input, select');
        inputs.forEach(input => {
            const key = input.id;
            if (key) {
                // Load saved value
                const saved = localStorage.getItem(key);
                if (saved !== null) {
                    if (input.type === 'checkbox') {
                        input.checked = saved === 'true';
                    } else {
                        input.value = saved;
                    }
                }
                
                // Save on change
                input.addEventListener('change', () => {
                    const value = input.type === 'checkbox' ? input.checked : input.value;
                    localStorage.setItem(key, value);
                });
            }
        });
    }

    loadSettings() {
        // Load backend URL if available
        const backendUrl = localStorage.getItem('backendUrl');
        if (backendUrl) {
            this.backendUrl = backendUrl;
        }
    }

    async onUrlChange(url) {
        if (!url || url.trim() === '') {
            this.hideVideoHeader();
            return;
        }

        try {
            this.showStatus('info', 'Fetching video information...', 'screenshots');
            
            const response = await fetch(`${this.backendUrl}/api/video-info`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url.trim() })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.showVideoHeader(data.thumbnail, data.title);
                this.updateResolutionOptions(data.videoResolutions, data.imageResolutions);
                this.showStatus('success', 'Video information loaded successfully', 'screenshots');
            } else {
                this.hideVideoHeader();
                this.showStatus('error', data.error || 'Failed to load video information', 'screenshots');
            }
        } catch (error) {
            console.error('Error fetching video info:', error);
            this.hideVideoHeader();
            this.showStatus('error', 'Failed to load video information. Please check your backend connection.', 'screenshots');
        }
    }

    showVideoHeader(thumbnail, title) {
        const header = document.getElementById('video-header');
        const thumbnailImg = document.getElementById('video-thumbnail');
        const titleDiv = document.getElementById('video-title');

        if (thumbnail) {
            thumbnailImg.src = thumbnail;
            thumbnailImg.style.display = 'block';
        } else {
            thumbnailImg.style.display = 'none';
        }

        if (title) {
            titleDiv.textContent = title;
        }

        header.style.display = 'flex';
    }

    hideVideoHeader() {
        document.getElementById('video-header').style.display = 'none';
    }

    updateResolutionOptions(videoResolutions, imageResolutions) {
        // Update video resolution dropdown
        const videoResSelect = document.getElementById('video-res');
        if (videoResolutions && videoResolutions.length > 0) {
            videoResSelect.innerHTML = '';
            videoResolutions.forEach(res => {
                const option = document.createElement('option');
                option.value = res;
                option.textContent = res;
                videoResSelect.appendChild(option);
            });
        }

        // Update image resolution dropdown
        const imageResSelect = document.getElementById('image-res');
        if (imageResolutions && imageResolutions.length > 0) {
            imageResSelect.innerHTML = '';
            imageResolutions.forEach(res => {
                const option = document.createElement('option');
                option.value = res;
                option.textContent = res;
                imageResSelect.appendChild(option);
            });
        }
    }

    async startScreenshots() {
        const url = document.getElementById('youtube-url').value;
        if (!url || url.trim() === '') {
            this.showStatus('error', 'Please enter a YouTube URL', 'screenshots');
            return;
        }

        const params = this.getScreenshotsParams();
        await this.startOperation('screenshots', params);
    }

    async startAudioDownload() {
        const url = document.getElementById('youtube-url').value;
        if (!url || url.trim() === '') {
            this.showStatus('error', 'Please enter a YouTube URL', 'audio');
            return;
        }

        const params = this.getAudioParams();
        await this.startOperation('audio', params);
    }

    async startVideoDownload() {
        const url = document.getElementById('youtube-url').value;
        if (!url || url.trim() === '') {
            this.showStatus('error', 'Please enter a YouTube URL', 'video');
            return;
        }

        const params = this.getVideoParams();
        await this.startOperation('video', params);
    }

    getScreenshotsParams() {
        return {
            url: document.getElementById('youtube-url').value,
            ffmpeg_path: document.getElementById('ffmpeg-path').value,
            image_res_label: document.getElementById('image-res').value,
            interval: parseFloat(document.getElementById('interval').value),
            mode_fast: document.getElementById('extraction-mode').value === 'Fast (FFmpeg)',
            save_to_folder: document.getElementById('save-to-folder').checked,
            user_folder: document.getElementById('folder-path').value,
            quality_preset: document.getElementById('quality-preset').value,
            container_pref: document.getElementById('container-pref').value,
            use_aria2c: document.getElementById('use-aria2c').checked,
            archive_enable: document.getElementById('archive-enable').checked
        };
    }

    getAudioParams() {
        return {
            url: document.getElementById('youtube-url').value,
            ffmpeg_path: document.getElementById('ffmpeg-path').value,
            audio_mode: document.getElementById('audio-format').value,
            bitrate_label: document.getElementById('audio-bitrate').value,
            save_to_folder: document.getElementById('save-to-folder').checked,
            user_folder: document.getElementById('folder-path').value,
            use_aria2c: document.getElementById('use-aria2c').checked,
            archive_enable: document.getElementById('archive-enable').checked
        };
    }

    getVideoParams() {
        return {
            url: document.getElementById('youtube-url').value,
            ffmpeg_path: document.getElementById('ffmpeg-path').value,
            video_res_label: document.getElementById('video-res').value,
            quality_preset: document.getElementById('quality-preset').value,
            container_pref: document.getElementById('container-pref').value,
            save_to_folder: document.getElementById('save-to-folder').checked,
            user_folder: document.getElementById('folder-path').value,
            use_aria2c: document.getElementById('use-aria2c').checked,
            archive_enable: document.getElementById('archive-enable').checked
        };
    }

    async startOperation(type, params) {
        try {
            this.showProgress(type, 0);
            this.showCancelButton(type, true);
            this.disableButtons(type, true);
            this.showStatus('info', 'Starting operation...', type);

            const response = await fetch(`${this.backendUrl}/api/${type}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.trim() === '') continue;
                    
                    try {
                        const data = JSON.parse(line);
                        this.handleOperationUpdate(type, data);
                    } catch (e) {
                        console.log('Raw chunk:', line);
                    }
                }
            }

        } catch (error) {
            console.error(`Error in ${type} operation:`, error);
            this.showStatus('error', `Operation failed: ${error.message}`, type);
            this.hideProgress(type);
            this.showCancelButton(type, false);
            this.disableButtons(type, false);
        }
    }

    handleOperationUpdate(type, data) {
        if (data.progress !== undefined) {
            this.updateProgress(type, data.progress);
        }

        if (data.status) {
            this.showStatus('info', data.status, type);
        }

        if (data.error) {
            this.showStatus('error', data.error, type);
            this.completeOperation(type, false);
            return;
        }

        if (data.complete) {
            this.completeOperation(type, true, data);
        }

        // Handle specific data for each type
        if (type === 'screenshots' && data.images) {
            this.updateScreenshotsGallery(data.images);
        }

        if (type === 'audio' && data.audio_file) {
            this.updateAudioPlayer(data.audio_file);
        }

        if (type === 'video' && data.video_file) {
            this.updateVideoPlayer(data.video_file);
        }
    }

    updateProgress(type, progress) {
        const progressBar = document.getElementById(`${type}-progress`);
        const progressFill = progressBar.querySelector('.progress-fill');
        const progressText = progressBar.querySelector('.progress-text');

        progressFill.style.width = `${progress}%`;
        progressText.textContent = `${progress}%`;
    }

    showProgress(type, initialProgress = 0) {
        const progressBar = document.getElementById(`${type}-progress`);
        progressBar.style.display = 'block';
        this.updateProgress(type, initialProgress);
    }

    hideProgress(type) {
        document.getElementById(`${type}-progress`).style.display = 'none';
    }

    showCancelButton(type, show) {
        const cancelBtn = document.getElementById(`cancel-${type}-btn`);
        cancelBtn.style.display = show ? 'inline-flex' : 'none';
    }

    disableButtons(type, disable) {
        const actionBtn = document.getElementById(`${type}-btn`);
        actionBtn.disabled = disable;
    }

    showStatus(type, message, tabType) {
        const statusElement = document.getElementById(`${tabType}-status`);
        statusElement.textContent = message;
        statusElement.className = `status-message ${type}`;
    }

    completeOperation(type, success, data = {}) {
        this.hideProgress(type);
        this.showCancelButton(type, false);
        this.disableButtons(type, false);

        if (success) {
            this.showStatus('success', 'Operation completed successfully!', type);
            this.showDownloadSection(type, data);
        }
    }

    showDownloadSection(type, data) {
        const downloadSection = document.getElementById(`${type}-download`);
        downloadSection.style.display = 'block';

        if (type === 'screenshots' && data.download_url) {
            const zipLink = document.getElementById('screenshots-zip');
            const backendUrl = this.getBackendUrl();
            zipLink.href = `${backendUrl}${data.download_url}`;
            zipLink.style.display = 'block';
        }

        if (type === 'audio' && data.download_url) {
            const audioLink = document.getElementById('audio-file');
            const backendUrl = this.getBackendUrl();
            audioLink.href = `${backendUrl}${data.download_url}`;
            audioLink.style.display = 'block';
        }

        if (type === 'video' && data.download_url) {
            const videoLink = document.getElementById('video-file');
            const backendUrl = this.getBackendUrl();
            videoLink.href = `${backendUrl}${data.download_url}`;
            videoLink.style.display = 'block';
        }
    }

    updateScreenshotsGallery(images) {
        const gallery = document.getElementById('screenshots-gallery');
        gallery.innerHTML = '';

        images.forEach(imagePath => {
            const img = document.createElement('img');
            img.src = imagePath;
            img.alt = 'Screenshot';
            img.onclick = () => window.open(imagePath, '_blank');
            gallery.appendChild(img);
        });
    }

    updateAudioPlayer(audioFile) {
        const audioPlayer = document.getElementById('audio-player');
        const audio = audioPlayer.querySelector('audio');
        audio.src = audioFile;
        audioPlayer.style.display = 'block';
    }

    updateVideoPlayer(videoFile) {
        const videoPlayer = document.getElementById('video-player');
        const video = videoPlayer.querySelector('video');
        video.src = videoFile;
        videoPlayer.style.display = 'block';
    }

    cancelOperation(type) {
        if (this.currentCancelEvent) {
            this.currentCancelEvent.set();
        }
        
        this.showStatus('info', 'Cancelling operation...', type);
        this.hideProgress(type);
        this.showCancelButton(type, false);
        this.disableButtons(type, false);
    }

    // Utility method to test backend connection
    async testBackendConnection() {
        try {
            const response = await fetch(`${this.backendUrl}/api/health`);
            return response.ok;
        } catch (error) {
            return false;
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.youtubeDownloader = new YouTubeDownloader();
    
    // Add a small indicator for backend connection status
    setInterval(async () => {
        const isConnected = await window.youtubeDownloader.testBackendConnection();
        const statusIndicator = document.querySelector('.app-header');
        
        if (statusIndicator) {
            if (isConnected) {
                statusIndicator.style.borderColor = '#10b981';
            } else {
                statusIndicator.style.borderColor = '#ef4444';
            }
        }
    }, 30000); // Check every 30 seconds
});

// Add some helpful console messages
console.log('YouTube Video Downloader PRO Frontend loaded');
console.log('Make sure your backend is running and accessible');
console.log('You can set BACKEND_URL environment variable or update localStorage.backendUrl');
