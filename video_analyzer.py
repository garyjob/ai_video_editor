#!/usr/bin/env python3
"""
Video analysis module using Whisper and YOLO.

Analyzes videos to extract transcripts and detect objects.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import subprocess

try:
    from logger_config import logger
except ImportError:
    import logging
    logger = logging.getLogger('video_analyzer')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def analyze_video(
    video_path: str,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Dict[str, Any]:
    """
    Analyze video using Whisper and YOLO.
    
    Args:
        video_path: Path to video file
        progress_callback: Callback function(step: str, progress: int)
    
    Returns:
        Analysis results in structured format
    """
    video_path_obj = Path(video_path)
    
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Get video metadata
    metadata = get_video_metadata(video_path)
    
    if progress_callback:
        progress_callback("Getting video metadata...", 10)
    
    # Transcribe with Whisper
    if progress_callback:
        progress_callback("Transcribing audio with Whisper...", 20)
    
    transcript_data = transcribe_with_whisper(video_path, progress_callback)
    transcript_segments = transcript_data.get('segments', [])
    transcript_text = transcript_data.get('text', '')
    logger.info(f"Whisper transcription complete: {len(transcript_segments)} segments, text length: {len(transcript_text)}")
    
    if len(transcript_segments) == 0 and len(transcript_text) == 0:
        logger.warning("Whisper returned no transcription - video may have no audio or speech. Will create time-based segments.")
        # Still create a valid transcript_data structure
        transcript_data = {
            "segments": [],
            "text": "",
            "language": "en"
        }
    
    # Detect objects with YOLO
    if progress_callback:
        progress_callback("Detecting objects with YOLO...", 60)
    
    objects_data = detect_objects_with_yolo(video_path, progress_callback)
    
    # Create segments
    if progress_callback:
        progress_callback("Creating segments...", 85)
    
    segments = create_segments(transcript_data, objects_data, metadata)
    
    if progress_callback:
        progress_callback("Finalizing analysis...", 95)
    
    # Build analysis result
    filename = video_path_obj.name
    result = {
        "file": filename,
        "path": str(video_path_obj.absolute()),
        "metadata": metadata,
        "segments": segments,
        "summary": {
            "main_topics": extract_topics(segments),
            "total_segments": len(segments),
            "total_duration": metadata.get("duration", 0),
            "object_types": list(set(obj["name"] for seg in segments for obj in seg.get("objects", []))),
            "average_quality": sum(seg.get("quality_score", 0.5) for seg in segments) / len(segments) if segments else 0.5
        }
    }
    
    if progress_callback:
        progress_callback("Complete", 100)
    
    return result


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """Get video metadata using ffprobe."""
    logger.debug(f"Getting metadata for: {Path(video_path).name}")
    try:
        import shutil
        # Find ffprobe in PATH or use default location
        ffprobe_path = shutil.which("ffprobe") or "/usr/local/bin/ffprobe"
        logger.debug(f"Using ffprobe: {ffprobe_path}")
        
        cmd = [
            ffprobe_path, "-v", "error", "-show_entries",
            "format=duration,size:stream=width,height,r_frame_rate,codec_name",
            "-of", "json", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        duration = float(data.get("format", {}).get("duration", 0))
        stream = data.get("streams", [{}])[0]
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        fps_str = stream.get("r_frame_rate", "30/1")
        fps_parts = fps_str.split("/")
        fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
        codec = stream.get("codec_name", "unknown")
        file_size = int(data.get("format", {}).get("size", 0))
        
        return {
            "duration": duration,
            "fps": fps,
            "resolution": f"{width}x{height}",
            "width": width,
            "height": height,
            "codec": codec,
            "file_size_mb": file_size / (1024 * 1024)
        }
    except Exception as e:
        logger.warning(f"Could not get metadata for {Path(video_path).name}: {e}", exc_info=True)
        return {
            "duration": 0,
            "fps": 30,
            "resolution": "unknown",
            "width": 0,
            "height": 0,
            "codec": "unknown",
            "file_size_mb": 0
        }


def transcribe_with_whisper(video_path: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """Transcribe video audio using Whisper."""
    logger.info(f"Starting Whisper transcription for: {Path(video_path).name}")
    try:
        import whisper
        import ssl
        import urllib.request
        
        # Fix SSL certificate issue for model download
        # This is a workaround for macOS SSL certificate verification issues
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Temporarily patch urllib for model download
            original_urlopen = urllib.request.urlopen
            def urlopen_with_ssl_bypass(*args, **kwargs):
                if 'context' not in kwargs:
                    kwargs['context'] = ssl_context
                return original_urlopen(*args, **kwargs)
            urllib.request.urlopen = urlopen_with_ssl_bypass
        except Exception:
            pass  # If SSL fix fails, continue anyway
        
        # Load Whisper model (base model for speed)
        logger.debug("Loading Whisper model 'base'...")
        if progress_callback:
            progress_callback("Loading Whisper model...", 25)
        
        model = whisper.load_model("base")
        logger.debug("Whisper model loaded successfully")
        
        # Restore original urlopen after model is loaded
        try:
            urllib.request.urlopen = original_urlopen
        except Exception:
            pass
        
        if progress_callback:
            progress_callback("Transcribing audio...", 35)
        
        # Transcribe with word timestamps
        logger.debug(f"Transcribing audio from: {video_path}")
        result = model.transcribe(
            video_path,
            word_timestamps=True,
            language="en"
        )
        
        logger.info(f"Whisper transcription successful: {len(result.get('segments', []))} segments, text length: {len(result.get('text', ''))}")
        return result
    except ImportError as e:
        logger.error("Whisper not installed", exc_info=True)
        raise ImportError("openai-whisper not installed. Run: pip install openai-whisper")
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        raise Exception(f"Whisper transcription failed: {e}")


def detect_objects_with_yolo(video_path: str, progress_callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Detect objects in video using YOLO."""
    try:
        from ultralytics import YOLO
        
        if progress_callback:
            progress_callback("Loading YOLO model...", 65)
        
        # Load YOLO model
        model = YOLO('yolov8n.pt')  # nano model for speed
        
        if progress_callback:
            progress_callback("Detecting objects in video...", 70)
        
        # Run detection on video (sample frames)
        results = model(video_path, verbose=False)
        
        # Extract detections (simplified - YOLO returns results per frame)
        detections = []
        # Note: YOLO video processing returns a generator or list of results
        # This is a simplified extraction
        frame_idx = 0
        for result in results:
            for box in result.boxes:
                detections.append({
                    "frame": frame_idx,
                    "time": frame_idx / 30.0,  # Approximate, assuming 30fps
                    "name": model.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "bbox": box.xyxy[0].tolist()
                })
            frame_idx += 1
        
        return detections
    except ImportError:
        raise ImportError("ultralytics not installed. Run: pip install ultralytics")
    except Exception as e:
        print(f"Warning: YOLO detection failed: {e}")
        return []  # Return empty list if YOLO fails


def create_segments(
    transcript_data: Dict[str, Any],
    objects_data: List[Dict[str, Any]],
    metadata: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Create segments from transcript and object data.
    
    Segments are 5-10 seconds, based on natural sentence breaks.
    """
    segments = []
    
    # Get transcript segments
    transcript_segments = transcript_data.get("segments", [])
    duration = metadata.get("duration", 0)
    
    logger.debug(f"create_segments: transcript_segments={len(transcript_segments)}, duration={duration:.2f}s")
    
    # If no transcript segments, create segments based on video duration
    if not transcript_segments:
        logger.warning(f"No transcript segments available - creating time-based segments for {duration:.2f}s video")
        # Create segments every 5 seconds
        segments = []
        segment_idx = 0
        for start in range(0, int(duration), 5):
            end = min(start + 5, duration)
            if end - start >= 1.0:  # Only create segments >= 1 second
                segment = {
                    "id": f"seg_{segment_idx:03d}",
                    "time_range": {
                        "start": float(start),
                        "end": float(end)
                    },
                    "duration": end - start,
                    "transcript": {
                        "full_text": "",
                        "words": [],
                        "language": transcript_data.get("language", "en")
                    },
                    "objects": [],
                    "priority": "medium",
                    "quality_score": 0.5,
                    "summary": f"Segment {start:.1f}s-{end:.1f}s (no audio detected)"
                }
                segments.append(segment)
                segment_idx += 1
        
        # Add objects to segments if available
        if objects_data:
            objects_by_time = {}
            for obj in objects_data:
                time_key = int(obj.get("time", 0))
                if time_key not in objects_by_time:
                    objects_by_time[time_key] = []
                objects_by_time[time_key].append(obj)
            
            for segment in segments:
                start = segment["time_range"]["start"]
                end = segment["time_range"]["end"]
                segment_objects = []
                for time_key, objs in objects_by_time.items():
                    if start <= time_key <= end:
                        for obj in objs:
                            segment_objects.append({
                                "name": obj.get("name", ""),
                                "confidence": obj.get("confidence", 0.5),
                                "time": obj.get("time", start),
                                "bbox": obj.get("bbox", [])
                            })
                segment["objects"] = segment_objects
        
        logger.info(f"Created {len(segments)} time-based segments (no audio)")
        return segments
    
    # Group objects by time
    objects_by_time = {}
    for obj in objects_data:
        time_key = int(obj.get("time", 0))
        if time_key not in objects_by_time:
            objects_by_time[time_key] = []
        objects_by_time[time_key].append(obj)
    
    logger.info(f"Creating segments from {len(transcript_segments)} transcript segments")
    
    # Create segments from transcript segments
    segment_idx = 0
    skipped_count = 0
    for transcript_seg in transcript_segments:
        start = transcript_seg.get("start", 0)
        end = transcript_seg.get("end", 0)
        text = transcript_seg.get("text", "").strip()
        
        # Skip very short segments
        if end - start < 1.0:
            skipped_count += 1
            logger.debug(f"Skipping short segment: {start:.2f}-{end:.2f}s (duration: {end-start:.2f}s)")
            continue
        
        # Get words with timestamps
        words = []
        for word_info in transcript_seg.get("words", []):
            words.append({
                "word": word_info.get("word", ""),
                "start": word_info.get("start", 0),
                "end": word_info.get("end", 0),
                "confidence": word_info.get("probability", 0.9)
            })
        
        # Get objects in this segment's time range
        segment_objects = []
        for time_key, objs in objects_by_time.items():
            if start <= time_key <= end:
                for obj in objs:
                    segment_objects.append({
                        "name": obj.get("name", ""),
                        "confidence": obj.get("confidence", 0.5),
                        "time": obj.get("time", start),
                        "bbox": obj.get("bbox", [])
                    })
        
        # Calculate quality score (simplified)
        quality_score = 0.5
        if words:
            avg_word_confidence = sum(w.get("confidence", 0.5) for w in words) / len(words)
            quality_score = 0.3 + (avg_word_confidence * 0.7)
        
        # Determine priority (simplified heuristic)
        priority = "medium"
        if start < 10 or (duration - end) < 10:  # Beginning or end
            priority = "high"
        elif len(text.split()) > 15:  # Longer sentences
            priority = "high"
        
        segment = {
            "id": f"seg_{segment_idx:03d}",
            "time_range": {
                "start": start,
                "end": end
            },
            "duration": end - start,
            "transcript": {
                "full_text": text,
                "words": words,
                "language": transcript_data.get("language", "en")
            },
            "objects": segment_objects,
            "priority": priority,
            "quality_score": quality_score,
            "summary": f"Segment at {start:.1f}s: {text[:50]}{'...' if len(text) > 50 else ''}"
        }
        
        segments.append(segment)
        segment_idx += 1
    
    logger.info(f"Created {len(segments)} segments from transcript (skipped {skipped_count} short segments)")
    if len(segments) == 0 and len(transcript_segments) > 0:
        logger.warning(f"No segments created! All {len(transcript_segments)} transcript segments were filtered out")
        logger.debug(f"Sample transcript segment: {json.dumps(transcript_segments[0] if transcript_segments else {}, indent=2)}")
    
    return segments


def extract_topics(segments: List[Dict[str, Any]]) -> List[str]:
    """Extract main topics from segments (simplified)."""
    # This is a simplified implementation
    # In a real implementation, you might use NLP techniques
    topics = []
    
    # Look for common words/phrases
    all_text = " ".join(seg.get("transcript", {}).get("full_text", "") for seg in segments).lower()
    
    # Simple keyword detection
    keywords = ["tutorial", "how to", "introduction", "demonstration", "explain", "guide"]
    for keyword in keywords:
        if keyword in all_text:
            topics.append(keyword.replace(" ", "_"))
    
    return topics[:5]  # Return top 5 topics


