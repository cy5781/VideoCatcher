# VideoCatcher 🎥

A powerful web application for downloading videos from YouTube, TikTok, and Instagram with a clean, modern interface.

## ✨ Features

- **Multi-Platform Support**: Download videos from YouTube, TikTok, and Instagram
- **Cookie Authentication**: Secure cookie-based authentication for YouTube and Instagram
- **Smart UI**: Dynamic interface that adapts based on selected platform
- **High Quality Downloads**: Multiple format and quality options
- **User-Friendly**: Clean, responsive design with step-by-step guides
- **Session Management**: Secure cookie handling with automatic expiration

## 🚀 Supported Platforms

| Platform | Cookie Required | Notes |
|----------|-----------------|-------|
| **YouTube** | ✅ Yes | Required for accessing content based on account permissions |
| **Instagram** | ✅ Yes | Required due to platform authentication requirements |
| **TikTok** | ❌ No | Direct download without authentication |

## 📋 Requirements

- Python 3.7+
- Flask
- yt-dlp
- Modern web browser

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd VideoCatcher
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   python3 app.py
   ```

5. **Access the application**
   - Open your browser and go to `http://localhost:5000`
   - Or use custom port: `PORT=5001 python3 app.py`

## 🍪 Cookie Setup Guide

### For YouTube & Instagram Downloads

#### Method 1: Browser Extension (Recommended)
1. Install "Get cookies.txt" extension for Chrome/Firefox
2. Navigate to YouTube or Instagram and log in
3. Click the extension icon
4. Export cookies in Netscape format
5. Upload the cookies.txt file in the app

#### Method 2: Developer Tools
1. Open YouTube/Instagram in your browser and log in
2. Press F12 to open Developer Tools
3. Go to Application/Storage tab → Cookies
4. Copy cookie data and format as Netscape cookies.txt
5. Upload to the app

### Cookie Security
- 🔒 Cookies are stored securely with 60-minute expiration
- 🔄 Re-upload when expired for continued access
- ⚠️ Never share your cookies with others

## 🎯 Usage

1. **Select Platform**: Choose YouTube, TikTok, or Instagram tab
2. **Upload Cookies** (if required): 
   - YouTube/Instagram: Upload your cookies.txt file
   - TikTok: Skip this step
3. **Enter URL**: Paste the video URL
4. **Download**: Click the download button

## 🎨 UI Features

- **Dynamic Interface**: Cookie sections automatically show/hide based on platform
- **Visual Feedback**: Button states indicate when cookies are required
- **Step-by-Step Guide**: Built-in 4-step cookie extraction guide
- **Responsive Design**: Works on desktop and mobile devices

## 🔧 Technical Details

### Architecture
- **Backend**: Flask web framework
- **Video Processing**: yt-dlp for video extraction
- **Frontend**: Vanilla JavaScript with modern CSS
- **Session Management**: Flask sessions with secure cookie storage

### Cookie Management
- Automatic validation and expiration (60 minutes)
- Secure file storage with unique user IDs
- Platform-specific authentication handling

### Download Strategies
- **Instagram**: Multiple user agents and API versions for reliability
- **YouTube**: Optimized format selection and quality options
- **TikTok**: Direct extraction without authentication

## 📁 Project Structure

```
VideoCatcher/
├── app.py                 # Main Flask application
├── templates/
│   ├── index.html        # Main UI template
│   ├── admin.html        # Admin interface
│   └── admin_login.html  # Admin login
├── cookies/              # User cookie storage
├── requirements.txt      # Python dependencies
├── test_*.py            # Test scripts
└── README.md            # This file
```

## 🚀 Recent Updates

- ✅ Added Instagram cookie requirement support
- ✅ Enhanced UI with dynamic platform-based sections
- ✅ Improved cookie validation and error handling
- ✅ Updated JavaScript for better user experience
- ✅ Added comprehensive cookie extraction guide

## 🛡️ Security & Privacy

- Cookies are stored locally and expire automatically
- No permanent storage of user credentials
- Session-based authentication with secure handling
- Regular cleanup of expired cookie files

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the terms specified in the LICENSE file.

## ⚠️ Disclaimer

This tool is for educational and personal use only. Please respect the terms of service of the platforms you're downloading from and ensure you have the right to download the content.

---

**Made with ❤️ for easy video downloading**