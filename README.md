# AI Video Editor - YouTube Shorts Creator

An intelligent video editing application that uses AI to analyze, edit, and upload videos to YouTube. Create engaging YouTube Shorts (15-60 seconds) from raw video footage with automated transcription, object detection, and AI-powered editing suggestions.

## 🎯 Purpose

This application streamlines the process of creating YouTube Shorts by:

1. **Analyzing Videos**: Automatically transcribes speech (Whisper) and detects objects (YOLO)
2. **AI-Powered Editing**: Uses Grok AI to suggest optimal video segments and editing strategies
3. **Automated Upload**: Uploads finished videos directly to your YouTube accounts
4. **Multi-Account Support**: Manage multiple YouTube accounts from one interface

## ✨ Features

- 🎬 **Video Queue System**: Process multiple videos in the background
- 🎤 **Speech Transcription**: Automatic transcription using OpenAI Whisper
- 👁️ **Object Detection**: Detect objects in videos using YOLOv8
- 🤖 **AI Editing Suggestions**: Grok AI suggests optimal cuts and segments
- 📹 **YouTube Shorts Format**: Optimized for 9:16 aspect ratio, 15-60 seconds
- 🔐 **Multi-Account Management**: Support for multiple YouTube accounts
- 📊 **Real-time Progress**: Track processing status with thumbnails and progress bars
- 📝 **Comprehensive Logging**: Detailed logs for debugging and monitoring

## 🏗️ Architecture

```
video_editor/
├── app.py                 # Flask web application
├── video_queue.py         # Background processing queue
├── video_analyzer.py      # Whisper + YOLO analysis
├── grok_client.py         # Grok AI integration
├── youtube_uploader.py   # YouTube API upload
├── oauth_flow.py         # OAuth authentication
├── logger_config.py       # Logging configuration
└── templates/            # HTML templates
```

## 🚀 Quick Start

### Prerequisites

**System Dependencies:**
- Python 3.11 or higher
- ffmpeg (for video processing) - `brew install ffmpeg` (macOS)
- cmake (for building dependencies) - `brew install cmake` (macOS)
- llvm (optional but recommended) - `brew install llvm` (macOS)

**Note:** See [SYSTEM_DEPENDENCIES.md](SYSTEM_DEPENDENCIES.md) for detailed installation instructions.

### Installation

1. **Install system dependencies first:**
   ```bash
   # macOS
   brew install ffmpeg cmake llvm
   
   # Linux (Ubuntu/Debian)
   sudo apt-get install ffmpeg cmake
   ```

2. **Clone the repository:**
   ```bash
   git clone git@github.com:garyjob/ai_video_editor.git
   cd ai_video_editor
   ```

3. **Run the setup script:**
   ```bash
   python3 setup.py
   ```
   
   This will:
   - Check for system dependencies
   - Create a virtual environment
   - Install all Python packages
   - Guide you through configuration
   
   **Note:** The setup script checks for system dependencies but does NOT install them automatically. Install them manually first (see step 1).

3. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate  # macOS/Linux
   # or
   .\venv\Scripts\activate   # Windows
   ```

4. **Start the application:**
   ```bash
   ./run.sh
   # or
   python app.py
   ```

5. **Open in browser:**
   ```
   http://localhost:8080
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Grok API Key (for AI processing)
GROK_API_KEY=your_grok_api_key_here

# Application Port (default: 8080)
PORT=8080
```

### YouTube OAuth Setup

1. **Get OAuth2 Credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project or select existing
   - Enable "YouTube Data API v3"
   - Create OAuth 2.0 credentials (Desktop app type)
   - Download the JSON file

2. **Add Account via Web UI:**
   - Start the application
   - Go to `http://localhost:8080/accounts`
   - Click "Authenticate with YouTube"
   - Follow the OAuth flow (email auto-detected)
   - Or upload credentials file manually

## 📖 Usage

### Creating YouTube Shorts

1. **Add Videos to Queue:**
   - Go to the main page (`http://localhost:8080`)
   - Click or drag & drop videos (up to 2 minutes each)
   - Click "Add to Queue"

2. **Wait for Analysis:**
   - Videos are analyzed in the background
   - Progress is shown in real-time
   - Thumbnails are generated automatically

3. **AI Processing:**
   - Once all videos are analyzed, click "Process with Grok"
   - Grok suggests optimal segments and editing strategy
   - Title, description, and tags are auto-generated

4. **Review & Upload:**
   - Review the suggested video segments
   - Edit title, description, and tags if needed
   - Select YouTube account
   - Click "Upload to YouTube"

### Workflow

```
Raw Videos → Queue → Analysis (Whisper + YOLO) → Grok AI → Review → YouTube Upload
```

## 🔧 System Requirements

### Python Packages
- Flask (web framework)
- OpenAI Whisper (speech transcription)
- Ultralytics YOLO (object detection)
- MoviePy (video editing)
- Google API Client (YouTube upload)
- Grok API client (AI processing)

### System Tools
- **ffmpeg**: Video processing and thumbnail generation
- **cmake**: Build tool for some dependencies
- **LLVM**: Required for numba/Whisper (usually auto-installed)

### Installation Commands

**macOS:**
```bash
brew install ffmpeg cmake
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ffmpeg cmake
```

**Windows:**
Download from official websites or use package managers like Chocolatey.

## 📁 Project Structure

```
ai_video_editor/
├── app.py                    # Main Flask application
├── video_queue.py            # Background processing queue
├── video_analyzer.py         # Video analysis (Whisper + YOLO)
├── grok_client.py           # Grok AI integration
├── youtube_uploader.py       # YouTube upload functionality
├── oauth_flow.py            # OAuth authentication
├── logger_config.py         # Logging configuration
├── setup.py                 # Setup script
├── run.sh                   # Run script
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not in git)
├── .gitignore              # Git ignore rules
├── credentials/            # YouTube credentials (not in git)
├── uploads/               # Uploaded videos (not in git)
├── logs/                  # Application logs (not in git)
└── templates/             # HTML templates
    ├── index.html         # Main page (unified workflow)
    ├── accounts.html      # Account management
    ├── oauth_success.html # OAuth success page
    └── oauth_error.html   # OAuth error page
```

## 🔒 Security

**Important:** Never commit sensitive files to git:

- ✅ `.env` - Environment variables (API keys)
- ✅ `credentials/` - YouTube OAuth credentials
- ✅ `uploads/` - User-uploaded videos
- ✅ `logs/` - Application logs

All sensitive files are excluded via `.gitignore`.

## 📊 Logging

The application includes comprehensive logging with **automatic file logging** for easy debugging:

- **Console**: Real-time logs with timestamps
- **File**: Detailed logs in `logs/video_editor_YYYYMMDD.log` (automatically created)
- **Levels**: DEBUG, INFO, WARNING, ERROR (with full stack traces)

### Viewing Logs

**Quick view (last 50 lines):**
```bash
./view_logs.sh
```

**View only errors:**
```bash
./view_logs.sh errors
```

**Real-time monitoring:**
```bash
tail -f logs/video_editor_$(date +%Y%m%d).log
```

**Full log file:**
```bash
./view_logs.sh full
```

### Sharing Logs for Debugging

When reporting issues, you can easily share the log file:
```bash
# Copy the log file path
echo "Log file: $(pwd)/logs/video_editor_$(date +%Y%m%d).log"

# Or view recent errors
./view_logs.sh errors
```

The log file contains:
- Full stack traces for all errors
- Timestamps for every operation
- File names and line numbers
- All API requests and responses
- Video processing progress

See [LOGGING.md](LOGGING.md) for more details.

## 🐛 Troubleshooting

### Common Issues

**1. "Could not find/load shared object file" (Whisper)**
- **Solution**: Reinstall llvmlite and numba:
  ```bash
  pip uninstall llvmlite numba
  pip install llvmlite numba --only-binary :all:
  ```

**2. "ffmpeg not found"**
- **Solution**: Install ffmpeg:
  ```bash
  brew install ffmpeg  # macOS
  sudo apt-get install ffmpeg  # Linux
  ```

**3. "SSL certificate verify failed" (Whisper model download)**
- **Solution**: The app includes SSL bypass for model download. If issues persist, check your network/firewall.

**4. NumPy version conflicts**
- **Solution**: The app uses NumPy 1.26.4 for compatibility. If you see conflicts, reinstall:
  ```bash
  pip install "numpy<2.0"
  ```

**5. OAuth "Access blocked" error**
- **Solution**: Add your email as a test user in Google Cloud Console:
  - Go to OAuth consent screen
  - Add test users
  - Wait a few minutes for changes to propagate

### Getting Help

1. Check the logs: `logs/video_editor_*.log`
2. Review error messages in the web UI
3. Check the console output when running the app

## 🛠️ Development

### Running in Development Mode

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

### Adding New Features

- Follow existing code patterns
- Add logging for new features
- Update README.md with new functionality
- Test with multiple video formats

## 📝 API Endpoints

### Video Processing
- `POST /api/queue/upload` - Upload videos to queue
- `GET /api/queue/status` - Get queue status
- `DELETE /api/queue/remove/<id>` - Remove from queue
- `GET /api/queue/result/<id>` - Get analysis result

### Account Management
- `GET /accounts` - Account management page
- `POST /api/accounts/add` - Add YouTube account
- `POST /api/accounts/delete` - Delete account
- `POST /api/accounts/authenticate` - Start OAuth flow
- `GET /oauth/callback` - OAuth callback handler

### YouTube Upload
- `POST /api/upload` - Upload video to YouTube

### Grok Processing
- `POST /api/grok/process` - Process videos with Grok AI

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Update documentation
6. Submit a pull request

## 📄 License

This project is private and proprietary.

## 👤 Author

Gary Job - [GitHub](https://github.com/garyjob)

## 🙏 Acknowledgments

- OpenAI Whisper for speech transcription
- Ultralytics YOLO for object detection
- Grok AI for intelligent video editing suggestions
- Google YouTube Data API for upload functionality

---

**Note**: This application processes videos locally. No video data is sent to external services except:
- Grok API (for editing suggestions - only analysis data, not video files)
- YouTube API (for final upload - only when you explicitly upload)
