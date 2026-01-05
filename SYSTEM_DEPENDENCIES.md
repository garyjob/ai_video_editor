# System Dependencies

This document lists all system-level dependencies required for the AI Video Editor.

## Required System Dependencies

### 1. ffmpeg
**Purpose:** Video processing, thumbnail generation, and metadata extraction

**Installation:**
- **macOS:** `brew install ffmpeg`
- **Linux (Ubuntu/Debian):** `sudo apt-get install ffmpeg`
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html)

**Verification:**
```bash
ffmpeg -version
ffprobe -version
```

### 2. cmake
**Purpose:** Required for building `llvmlite` (dependency of `numba` and `whisper`)

**Installation:**
- **macOS:** `brew install cmake`
- **Linux (Ubuntu/Debian):** `sudo apt-get install cmake`
- **Windows:** Download from [cmake.org](https://cmake.org/download/)

**Verification:**
```bash
cmake --version
```

### 3. llvm (Optional but Recommended)
**Purpose:** Helps build `llvmlite` more reliably

**Installation:**
- **macOS:** `brew install llvm`
- **Linux:** Usually comes with development tools
- **Windows:** Usually not needed (pre-built wheels available)

**Verification:**
```bash
llvm-config --version
```

## Python Dependencies

All Python dependencies are listed in `requirements.txt` and installed automatically by `setup.py`:

```bash
pip install -r requirements.txt
```

Key packages:
- `flask` - Web framework
- `openai-whisper` - Speech transcription
- `ultralytics` - YOLO object detection
- `moviepy` - Video editing
- `google-api-python-client` - YouTube upload
- And more...

## Installation Order

1. **Install system dependencies first:**
   ```bash
   # macOS
   brew install ffmpeg cmake llvm
   
   # Linux
   sudo apt-get install ffmpeg cmake
   ```

2. **Then run setup.py:**
   ```bash
   python3 setup.py
   ```

   This will:
   - Create virtual environment
   - Install Python packages
   - Check for system dependencies
   - Guide you through configuration

## Troubleshooting

### "ffmpeg not found" error
- Make sure ffmpeg is installed and in your PATH
- On macOS, Homebrew usually adds it to `/usr/local/bin/ffmpeg`
- The app will also check `/usr/local/bin/ffmpeg` as a fallback

### "cmake not found" during pip install
- Install cmake before running `setup.py`
- Some packages (like `llvmlite`) require cmake to build from source

### "Could not find LLVM" error
- Install llvm: `brew install llvm` (macOS)
- Or use pre-built wheels: `pip install llvmlite --only-binary :all:`

### Architecture mismatches (arm64 vs x86_64)
- Make sure Python and all dependencies use the same architecture
- On Apple Silicon, use native arm64 Python or x86_64 via Rosetta consistently

## Notes

- **Model files are NOT installed:** Whisper and YOLO models are downloaded automatically on first use
- **First run is slow:** Initial model downloads can take several minutes
- **Internet required:** First-time setup requires internet for:
  - Python package downloads
  - Whisper model download (~500MB)
  - YOLO model download (~6MB)

