# Logging Configuration

The video editor application includes comprehensive logging to help with debugging and monitoring.

## Log File Location

Logs are stored in the `logs/` directory with daily rotation:
- Format: `logs/video_editor_YYYYMMDD.log`
- Example: `logs/video_editor_20260104.log`

## Log Levels

- **DEBUG**: Detailed information for diagnosing problems
- **INFO**: General informational messages about application flow
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages with full stack traces

## What Gets Logged

### Application Startup
- Application initialization
- Configuration paths (upload folder, thumbnails folder)
- Startup timestamp

### Video Upload & Queue
- Files received for upload
- Files saved to disk
- Videos added to processing queue
- Queue status requests

### Video Processing
- Video analysis start/completion
- Whisper model loading
- Transcription progress
- YOLO object detection
- Thumbnail generation
- Metadata extraction
- Processing errors with full stack traces

### Account Management
- Account addition requests
- OAuth authentication flow
- Credential file operations

### API Requests
- All API endpoint calls
- Request parameters
- Response status

## Viewing Logs

### Real-time Logs (Console)
Logs are displayed in the console/terminal where you run the Flask app.

### Log Files
View the latest log file:
```bash
tail -f logs/video_editor_$(date +%Y%m%d).log
```

View all logs:
```bash
cat logs/video_editor_*.log
```

Search for errors:
```bash
grep ERROR logs/video_editor_*.log
```

## Log Format

### Console Format (Simplified)
```
HH:MM:SS - LEVEL - Message
```

### File Format (Detailed)
```
YYYY-MM-DD HH:MM:SS - logger_name - LEVEL - [filename.py:line_number] - Message
```

## Example Log Messages

```
2026-01-04 21:30:15 - video_editor - INFO - [app.py:432] - Received request to upload videos to queue
2026-01-04 21:30:15 - video_editor - INFO - [app.py:437] - Received 3 file(s) for upload
2026-01-04 21:30:16 - video_editor - INFO - [video_queue.py:73] - Adding 3 video(s) to queue
2026-01-04 21:30:16 - video_editor - INFO - [video_queue.py:97] - Added video to queue: IMG_5907.MOV (ID: abc123)
2026-01-04 21:30:17 - video_editor - INFO - [video_analyzer.py:29] - Starting video analysis: IMG_5907.MOV
2026-01-04 21:30:18 - video_editor - INFO - [video_analyzer.py:44] - Starting Whisper transcription...
2026-01-04 21:30:25 - video_editor - INFO - [video_analyzer.py:155] - Whisper transcription successful: 15 segments, text length: 234
```

## Troubleshooting

When reporting issues, please include:
1. The relevant log entries from the log file
2. The timestamp when the issue occurred
3. Any ERROR or WARNING messages

The log files contain full stack traces for errors, making it easier to diagnose problems.

