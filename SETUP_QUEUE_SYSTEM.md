# Video Queue System Setup Guide

## Overview

The video queue system allows you to:
1. Add multiple videos to a processing queue
2. Automatically analyze videos in the background (Whisper + YOLO)
3. Process analyzed videos with Grok to generate editing suggestions
4. Create YouTube Shorts (15-60 seconds, vertical format)

## Installation

### 1. Install Dependencies

```bash
cd /Users/garyjob/Applications/video_editor
source venv/bin/activate
pip install -r requirements.txt
```

**Note:** First-time installation will download:
- Whisper model (~150MB for base model)
- YOLO model (~6MB for nano model)
- Other dependencies

### 2. Ensure FFmpeg is Installed

FFmpeg is required for video metadata extraction:

```bash
# macOS
brew install ffmpeg

# Or check if already installed
ffmpeg -version
```

### 3. Environment Variables

The `.env` file is already created with the Grok API key. If needed, you can verify:

```bash
cat .env
```

Key environment variables:
- `GROK_API_KEY` - Your Grok API key (already configured)
- `PORT` - Flask server port (default: 8080)
- `MAX_CONCURRENT_ANALYSIS` - Max concurrent video analyses (default: 2)

## Usage

### 1. Start the Server

```bash
cd /Users/garyjob/Applications/video_editor
source venv/bin/activate
python app.py
```

Or use the run script:
```bash
./run.sh
```

### 2. Access the Processing Page

Open your browser and navigate to:
```
http://localhost:8080/process
```

### 3. Add Videos to Queue

1. Enter video paths in the textarea (one per line):
   ```
   /Users/garyjob/Downloads/video1.mp4
   /Users/garyjob/Downloads/video2.mp4
   /Users/garyjob/Downloads/video3.mp4
   ```

2. Click "➕ Add to Queue"

3. Videos are automatically analyzed in the background

### 4. Monitor Progress

- **Queued** ⏸️ - Waiting to start
- **Processing** ⏳ - Currently analyzing
  - Shows progress bar and current step (Whisper/YOLO)
- **Complete** ✅ - Analysis finished
- **Error** ❌ - Processing failed (check error message)

### 5. Process with Grok

Once all videos are analyzed:
1. Click "🎬 Process with Grok"
2. Grok analyzes all segments and generates:
   - Editing plan (selected segments, sequence, transitions)
   - Title, description, and tags for YouTube Shorts
   - Duration target: 15-60 seconds

### 6. Review and Upload

(Next step - review page to be implemented)

## API Endpoints

### Queue Management

- `POST /api/queue/add` - Add videos to queue
  ```json
  {
    "paths": ["/path/to/video1.mp4", "/path/to/video2.mp4"]
  }
  ```

- `GET /api/queue/status` - Get queue status
  ```json
  {
    "queue": [...],
    "results": {...},
    "processing_count": 1,
    "queue_length": 3
  }
  ```

- `DELETE /api/queue/remove/<item_id>` - Remove item from queue

- `GET /api/queue/result/<item_id>` - Get analysis result

### Grok Processing

- `POST /api/grok/process` - Process analyzed videos with Grok
  ```json
  {
    "target_duration_min": 15,
    "target_duration_max": 60
  }
  ```

## Architecture

### Components

1. **video_queue.py** - Queue management system
   - Thread-safe queue
   - Background processing
   - Status tracking

2. **video_analyzer.py** - Video analysis
   - Whisper for transcription
   - YOLO for object detection
   - Segment creation

3. **grok_client.py** - Grok API integration
   - Analysis data → Grok
   - Editing plan generation
   - Metadata generation

4. **app.py** - Flask routes
   - Queue endpoints
   - Grok processing endpoint
   - Process page route

## Troubleshooting

### "Whisper model not found"
- First run downloads models automatically
- Check internet connection
- Models are cached after first download

### "YOLO model not found"
- First run downloads models automatically
- Check internet connection

### "FFmpeg not found"
- Install FFmpeg: `brew install ffmpeg`
- Verify: `ffmpeg -version`

### "GROK_API_KEY not configured"
- Check `.env` file exists
- Verify API key is set
- Restart server after changing .env

### Analysis takes too long
- Normal for first run (model downloads)
- Each 2-minute video takes ~45-80 seconds
- Multiple videos process concurrently (max 2 by default)

### Queue not processing
- Check server logs for errors
- Verify video paths are valid
- Check file permissions

## Performance Notes

- **Per video (2 minutes)**:
  - Whisper: ~30-60 seconds
  - YOLO: ~10-20 seconds
  - Total: ~45-80 seconds

- **5 videos**:
  - Analysis: ~4-7 minutes (with concurrency)
  - Grok processing: ~10-30 seconds
  - Total: ~6-10 minutes

- **Model sizes**:
  - Whisper base: ~150MB
  - YOLO nano: ~6MB

## Next Steps

1. ✅ Queue system implemented
2. ✅ Video analysis (Whisper + YOLO)
3. ✅ Grok integration
4. ⏳ Review/approval page
5. ⏳ Video editing (apply Grok suggestions)
6. ⏳ YouTube upload integration


