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
    progress_callback: Optional[Callable[[str, int], None]] = None,
    enrich_visual_dynamics: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Analyze video using Whisper and YOLO.
    
    Args:
        video_path: Path to video file
        progress_callback: Callback function(step: str, progress: int)
        enrich_visual_dynamics: If True, add FFmpeg scene-cut + OpenCV motion scores
            and per-segment editor_score. If None, uses env VIDEO_ENRICH=1 or true.
    
    Returns:
        Analysis results in structured format
    """
    video_path_obj = Path(video_path)
    
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Get video metadata
    metadata = get_video_metadata(video_path)
    original_duration = metadata.get("duration", 0)
    max_duration_seconds = 300  # 5 minutes
    
    # Limit analysis to max_duration_seconds for long videos
    if original_duration > max_duration_seconds:
        logger.info(f"Video duration ({original_duration:.1f}s) exceeds limit ({max_duration_seconds}s). Analyzing first {max_duration_seconds}s only.")
        metadata["duration"] = max_duration_seconds
        metadata["truncated"] = True
        metadata["original_duration"] = original_duration
    else:
        metadata["truncated"] = False
    
    if progress_callback:
        progress_callback("Getting video metadata...", 10)
    
    # Transcribe with Whisper
    if progress_callback:
        progress_callback("Transcribing audio with Whisper...", 20)
    
    transcript_data = transcribe_with_whisper(video_path, progress_callback, max_duration=max_duration_seconds)
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
    
    objects_data = detect_objects_with_yolo(video_path, progress_callback, max_duration=max_duration_seconds)
    
    # Create segments
    if progress_callback:
        progress_callback("Creating segments...", 85)
    
    segments = create_segments(transcript_data, objects_data, metadata)

    # Optional: scene-change + motion enrichment for ranking / Grok
    if enrich_visual_dynamics is None:
        enrich_visual_dynamics = os.environ.get("VIDEO_ENRICH", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    scene_change_times: List[float] = []
    if enrich_visual_dynamics:
        try:
            from segment_enrichment import enrich_analysis_result as _enrich_visual

            partial = {
                "path": str(video_path_obj.absolute()),
                "metadata": metadata,
                "segments": segments,
                "file": video_path_obj.name,
                "summary": {},
            }
            partial = _enrich_visual(partial, progress_callback=progress_callback)
            segments = partial.get("segments", segments)
            scene_change_times = partial.get("scene_change_times", [])
        except Exception as e:
            logger.warning("Visual dynamics enrichment skipped: %s", e, exc_info=True)
    
    if progress_callback:
        progress_callback("Finalizing analysis...", 95)
    
    # Extract video context/purpose using combined analysis
    if progress_callback:
        progress_callback("Analyzing video context...", 98)
    
    try:
        video_context = extract_video_context(segments, transcript_data, objects_data, metadata)
    except Exception as e:
        logger.error(f"Error extracting video context: {e}", exc_info=True)
        # Provide fallback context if extraction fails
        video_context = {
            "has_audio": len(transcript_data.get("text", "")) > 0,
            "has_visual_content": len(objects_data) > 0,
            "duration_category": "unknown",
            "content_type": "general",
            "narrative_structure": {"structure": "unknown"},
            "key_elements": {},
            "purpose_indicators": ["general_content"],
            "scene_description": "Analysis incomplete"
        }
    
    # Build analysis result
    filename = video_path_obj.name
    summary = {
        "main_topics": extract_topics(segments),
        "total_segments": len(segments),
        "total_duration": metadata.get("duration", 0),
        "original_duration": metadata.get("original_duration", metadata.get("duration", 0)),
        "was_truncated": metadata.get("truncated", False),
        "object_types": list(set(obj["name"] for seg in segments for obj in seg.get("objects", []))),
        "average_quality": sum(seg.get("quality_score", 0.5) for seg in segments) / len(segments) if segments else 0.5
    }
    if enrich_visual_dynamics and segments:
        eds = [float(s.get("editor_score", 0)) for s in segments]
        summary["average_editor_score"] = sum(eds) / len(eds) if eds else 0.0
        summary["scene_cut_count"] = len(scene_change_times)

    result = {
        "file": filename,
        "path": str(video_path_obj.absolute()),
        "metadata": metadata,
        "segments": segments,
        "context": video_context,  # New: video purpose/context
        "summary": summary,
    }
    if scene_change_times:
        result["scene_change_times"] = scene_change_times
    
    if progress_callback:
        progress_callback("Complete", 100)
    
    if metadata.get("truncated"):
        logger.info(f"Analysis complete for {filename}: {len(segments)} segments from first {max_duration_seconds}s (original: {original_duration:.1f}s)")
    else:
        logger.info(f"Analysis complete for {filename}: {len(segments)} segments")
    
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
        if len(fps_parts) == 2 and float(fps_parts[1]) != 0:
            fps = float(fps_parts[0]) / float(fps_parts[1])
        else:
            fps = 30.0  # Default fallback
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


def transcribe_with_whisper(video_path: str, progress_callback: Optional[Callable] = None, max_duration: int = 300) -> Dict[str, Any]:
    """Transcribe video audio using Whisper.
    
    Args:
        video_path: Path to video file
        progress_callback: Optional progress callback
        max_duration: Maximum duration in seconds to transcribe (default: 300 = 5 minutes)
    """
    logger.info(f"Starting Whisper transcription for: {Path(video_path).name} (max {max_duration}s)")
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
        # For long videos, extract audio segment first
        logger.debug(f"Transcribing audio from: {video_path} (max {max_duration}s)")
        
        # Check if we need to limit duration
        import subprocess
        import shutil
        ffprobe_path = shutil.which("ffprobe") or "/usr/local/bin/ffprobe"
        duration_check = subprocess.run(
            [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True,
            text=True
        )
        
        video_duration = 0
        if duration_check.returncode == 0:
            try:
                video_duration = float(duration_check.stdout.strip())
            except:
                pass
        
        # If video is longer than max_duration, create a temporary trimmed version
        temp_video = None
        if video_duration > max_duration:
            logger.info(f"Video is {video_duration:.1f}s, creating {max_duration}s segment for transcription")
            import tempfile
            ffmpeg_path = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            temp_video.close()
            
            # Extract first max_duration seconds
            trim_cmd = [
                ffmpeg_path, "-i", video_path,
                "-t", str(max_duration),
                "-c", "copy",  # Copy codec (fast)
                "-y",  # Overwrite
                temp_video.name
            ]
            trim_result = subprocess.run(trim_cmd, capture_output=True, text=True)
            if trim_result.returncode != 0:
                logger.warning(f"Could not trim video, using full video: {trim_result.stderr}")
                temp_video = None
            else:
                logger.debug(f"Created trimmed video: {temp_video.name}")
        
        video_to_transcribe = temp_video.name if temp_video else video_path
        
        result = model.transcribe(
            video_to_transcribe,
            word_timestamps=True,
            language=None,  # Auto-detect language (more accurate)
            verbose=False,
            fp16=False  # Use fp32 for better compatibility
        )
        
        # Perform speaker diarization if available
        speaker_labels = None
        try:
            speaker_labels = perform_speaker_diarization(video_to_transcribe, progress_callback)
            if speaker_labels:
                logger.info(f"Speaker diarization complete: {len(speaker_labels)} speaker segments identified")
                # Merge speaker labels with transcription segments
                result = merge_speaker_labels(result, speaker_labels)
        except Exception as e:
            logger.warning(f"Speaker diarization failed (continuing without it): {e}")
            # Continue without speaker labels if diarization fails
        
        # Clean up temp file
        if temp_video and os.path.exists(temp_video.name):
            os.unlink(temp_video.name)
        
        # Log transcription details
        detected_language = result.get('language', 'unknown')
        text_length = len(result.get('text', ''))
        segments_count = len(result.get('segments', []))
        speaker_count = result.get('speaker_count', 0)
        logger.info(f"Whisper detected language: {detected_language}, text: '{result.get('text', '')[:100]}...' (length: {text_length})")
        if speaker_count > 0:
            logger.info(f"Detected {speaker_count} distinct speaker(s)")
        
        if text_length == 0:
            logger.warning(f"No text transcribed - video may have no audio track or speech")
        
        logger.info(f"Whisper transcription successful: {len(result.get('segments', []))} segments, text length: {len(result.get('text', ''))}")
        return result
    except ImportError as e:
        logger.error("Whisper not installed", exc_info=True)
        raise ImportError("openai-whisper not installed. Run: pip install openai-whisper")
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        raise Exception(f"Whisper transcription failed: {e}")


def perform_speaker_diarization(audio_path: str, progress_callback: Optional[Callable] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Perform speaker diarization to identify different speakers in audio.
    
    Args:
        audio_path: Path to audio/video file
        progress_callback: Optional progress callback
    
    Returns:
        List of speaker segments with start, end, and speaker_id, or None if diarization fails
    """
    try:
        from pyannote.audio import Pipeline
        import torch
        
        if progress_callback:
            progress_callback("Identifying speakers...", 40)
        
        logger.debug("Loading speaker diarization model...")
        
        # Try to load pyannote speaker diarization pipeline
        # Note: This requires Hugging Face authentication token for the first run
        # Users need to accept model terms at: https://huggingface.co/pyannote/speaker-diarization-3.1
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=None  # Will prompt if needed, or set HF_TOKEN env var
            )
        except Exception as e:
            logger.warning(f"Could not load pyannote model (may need Hugging Face token): {e}")
            logger.info("Speaker diarization requires Hugging Face authentication. Set HF_TOKEN environment variable or accept model terms.")
            return None
        
        # Run diarization
        logger.debug(f"Running speaker diarization on: {Path(audio_path).name}")
        diarization = pipeline(audio_path)
        
        # Extract speaker segments
        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker_id": speaker
            })
        
        logger.info(f"Speaker diarization identified {len(set(seg['speaker_id'] for seg in speaker_segments))} distinct speaker(s)")
        return speaker_segments
        
    except ImportError:
        logger.debug("pyannote.audio not installed - speaker diarization unavailable")
        logger.info("To enable speaker diarization, install: pip install pyannote.audio")
        return None
    except Exception as e:
        logger.warning(f"Speaker diarization failed: {e}", exc_info=True)
        return None


def merge_speaker_labels(transcription_result: Dict[str, Any], speaker_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge speaker diarization labels with Whisper transcription segments.
    
    Args:
        transcription_result: Whisper transcription result
        speaker_segments: List of speaker segments from diarization
    
    Returns:
        Transcription result with speaker labels added to segments
    """
    if not speaker_segments:
        return transcription_result
    
    # Create a mapping of time to speaker
    speaker_map = {}
    for seg in speaker_segments:
        # Round to nearest 0.1 second for matching
        start_key = round(seg["start"], 1)
        end_key = round(seg["end"], 1)
        for t in range(int(start_key * 10), int(end_key * 10) + 1):
            speaker_map[t / 10.0] = seg["speaker_id"]
    
    # Assign speakers to transcription segments
    segments = transcription_result.get('segments', [])
    speakers_found = set()
    
    for segment in segments:
        segment_start = segment.get('start', 0)
        segment_end = segment.get('end', segment_start)
        
        # Find the most common speaker in this segment
        speaker_counts = {}
        for t in range(int(segment_start * 10), int(segment_end * 10) + 1):
            speaker = speaker_map.get(t / 10.0)
            if speaker:
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
        
        if speaker_counts:
            # Assign the most common speaker
            assigned_speaker = max(speaker_counts.items(), key=lambda x: x[1])[0]
            segment['speaker'] = assigned_speaker
            speakers_found.add(assigned_speaker)
        else:
            # No speaker found for this segment
            segment['speaker'] = None
    
    # Update result with speaker information
    transcription_result['speaker_count'] = len(speakers_found)
    transcription_result['speakers'] = sorted(list(speakers_found))
    
    logger.debug(f"Merged speaker labels: {len(speakers_found)} speakers identified across {len(segments)} segments")
    
    return transcription_result


def detect_objects_with_yolo(video_path: str, progress_callback: Optional[Callable] = None, max_duration: int = 300) -> List[Dict[str, Any]]:
    """Detect objects in video using YOLO.
    
    Args:
        video_path: Path to video file
        progress_callback: Optional progress callback
        max_duration: Maximum duration in seconds to process (default: 300 = 5 minutes)
    """
    try:
        from ultralytics import YOLO
        
        if progress_callback:
            progress_callback("Loading YOLO model...", 65)
        
        logger.debug(f"Loading YOLO model for: {Path(video_path).name}")
        
        # Load YOLO model
        model = YOLO('yolov8n.pt')  # nano model for speed
        
        if progress_callback:
            progress_callback("Detecting objects in video...", 70)
        
        logger.debug(f"Running YOLO detection on video: {Path(video_path).name}")
        
        # Use frame sampling instead of full video processing to avoid hanging
        # Sample every Nth frame to speed up processing
        try:
            import cv2
        except ImportError:
            logger.warning("OpenCV (cv2) not available, using limited YOLO processing")
            # Fallback: use YOLO directly but with timeout protection
            results = model(video_path, verbose=False, max_det=10)
            detections = []
            frame_idx = 0
            max_frames = 100  # Very limited
            
            for result in results:
                if frame_idx >= max_frames:
                    break
                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        detections.append({
                            "frame": frame_idx,
                            "time": frame_idx / 30.0,
                            "name": model.names[int(box.cls)],
                            "confidence": float(box.conf),
                            "bbox": box.xyxy[0].tolist()
                        })
                frame_idx += 1
            
            logger.info(f"YOLO detection complete (fallback): {len(detections)} objects")
            return detections
        
        logger.debug("Opening video with OpenCV for frame sampling")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning(f"Could not open video with OpenCV: {video_path}")
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        logger.debug(f"Video: {total_frames} frames, {fps:.1f} fps, {duration:.1f}s duration")
        
        # Limit processing to max_duration
        effective_duration = min(duration, max_duration)
        
        if effective_duration < duration:
            logger.info(f"Video duration ({duration:.1f}s) exceeds limit ({max_duration}s). Processing first {max_duration}s only.")
        
        # Smart frame sampling for videos of any length:
        # - Short videos (< 30s): Sample every 0.5 seconds (2 fps)
        # - Medium videos (30s - 2min): Sample every 1 second (1 fps)
        # - Long videos (> 2min): Sample every 2 seconds (0.5 fps)
        # Always process at least first 30 seconds for context, but respect max_duration
        if effective_duration <= 30:
            sample_interval = max(1, int(fps / 2))  # 2 frames per second
            max_seconds_to_process = effective_duration  # Process entire video
        elif effective_duration <= 120:
            sample_interval = max(1, int(fps))  # 1 frame per second
            max_seconds_to_process = min(60, effective_duration)  # Process up to 60 seconds
        else:
            sample_interval = max(1, int(fps * 2))  # 1 frame every 2 seconds
            max_seconds_to_process = min(max_duration, effective_duration)  # Process up to max_duration
        
        max_frames_to_process = int(fps * max_seconds_to_process)
        
        logger.info(f"Video duration: {duration:.1f}s - Sampling strategy: {sample_interval} frame interval, processing up to {max_seconds_to_process}s ({max_frames_to_process} frames)")
        
        detections = []
        frame_idx = 0
        processed_count = 0
        
        logger.debug(f"Sampling every {sample_interval} frames, max {max_frames_to_process} frames")
        
        while processed_count < max_frames_to_process:
            ret, frame = cap.read()
            if not ret:
                logger.debug(f"Reached end of video at frame {frame_idx}")
                break
            
            # Only process sampled frames
            if frame_idx % sample_interval == 0:
                if progress_callback:
                    # Update progress more frequently for longer videos
                    update_frequency = max(1, processed_count // 20) if processed_count > 20 else 1
                    if processed_count % update_frequency == 0 or processed_count < 5:
                        progress = 70 + int((processed_count / max_frames_to_process) * 25)  # Use 25% of progress bar (70-95%)
                        time_processed = (frame_idx / fps) if fps > 0 else 0
                        progress_callback(f"Detecting objects... {time_processed:.1f}s / {max_seconds_to_process:.1f}s", progress)
                
                # Run YOLO on this frame
                results = model(frame, verbose=False, max_det=10)
                
                # Extract detections from this frame
                for result in results:
                    if result.boxes is not None and len(result.boxes) > 0:
                        for box in result.boxes:
                            detections.append({
                                "frame": frame_idx,
                                "time": frame_idx / fps,
                                "name": model.names[int(box.cls)],
                                "confidence": float(box.conf),
                                "bbox": box.xyxy[0].tolist()
                            })
                
                processed_count += 1
            
            frame_idx += 1
        
        cap.release()
        
        # For longer videos, also sample some frames from the middle and end for better coverage
        if duration > 60 and processed_count < max_frames_to_process:
            logger.debug(f"Video is long ({duration:.1f}s), sampling additional frames from middle and end")
            # This could be added later if needed, but current sampling should be sufficient
        
        logger.info(f"YOLO detection complete: {len(detections)} objects detected in {processed_count} sampled frames (from {frame_idx} total frames, {duration:.1f}s video)")
        return detections
    except ImportError:
        logger.error("ultralytics not installed", exc_info=True)
        raise ImportError("ultralytics not installed. Run: pip install ultralytics")
    except Exception as e:
        logger.warning(f"YOLO detection failed: {e}", exc_info=True)
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


def extract_video_context(
    segments: List[Dict[str, Any]],
    transcript_data: Dict[str, Any],
    objects_data: List[Dict[str, Any]],
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract video context, purpose, and 'why' the video is happening.
    
    Uses combined analysis of:
    - Transcript (what's being said)
    - Objects (what's visible)
    - Visual cues (scene composition)
    - Duration and structure
    
    Returns context including purpose, narrative, and key themes.
    """
    logger.debug("Extracting video context from combined analysis")
    
    # Collect all transcript text
    all_transcript = " ".join(
        seg.get("transcript", {}).get("full_text", "") 
        for seg in segments 
        if seg.get("transcript", {}).get("full_text", "").strip()
    ).strip()
    
    # Collect all detected objects
    all_objects = list(set(
        obj["name"] 
        for seg in segments 
        for obj in seg.get("objects", [])
    ))
    
    # Analyze structure
    duration = metadata.get("duration", 0)
    segment_count = len(segments)
    has_speech = len(all_transcript) > 0
    has_objects = len(all_objects) > 0
    
    # Build context analysis
    context = {
        "has_audio": has_speech,
        "has_visual_content": has_objects,
        "duration_category": (
            "very_short" if duration < 10 else
            "short" if duration < 30 else
            "medium" if duration < 120 else
            "long"
        ),
        "content_type": _infer_content_type(all_transcript, all_objects, segments),
        "narrative_structure": _analyze_narrative(segments),
        "key_elements": {
            "spoken_content": all_transcript[:200] + "..." if len(all_transcript) > 200 else all_transcript,
            "visual_elements": all_objects,
            "main_objects": all_objects[:5] if len(all_objects) > 5 else all_objects
        },
        "purpose_indicators": _extract_purpose_indicators(all_transcript, all_objects, segments),
        "scene_description": _describe_scene(all_transcript, all_objects, duration)
    }
    
    logger.info(f"Video context extracted: {context.get('content_type', 'unknown')} - {context.get('scene_description', '')[:50]}...")
    
    return context


def _infer_content_type(transcript: str, objects: List[str], segments: List[Dict]) -> str:
    """Infer the type of video content."""
    transcript_lower = transcript.lower()
    
    # Check for common video types
    if any(word in transcript_lower for word in ["tutorial", "how to", "learn", "guide", "step"]):
        return "tutorial"
    elif any(word in transcript_lower for word in ["review", "opinion", "thoughts", "rating"]):
        return "review"
    elif any(word in transcript_lower for word in ["unboxing", "opening", "new", "just got"]):
        return "unboxing"
    elif any(word in transcript_lower for word in ["vlog", "day in", "my life", "update"]):
        return "vlog"
    elif "person" in objects or "people" in objects:
        return "people_content"
    elif "food" in objects or "dish" in objects:
        return "food_content"
    elif len(segments) == 0 or len(transcript) == 0:
        return "visual_only"
    else:
        return "general"


def _analyze_narrative(segments: List[Dict]) -> Dict[str, Any]:
    """Analyze narrative structure of the video."""
    if not segments:
        return {"structure": "no_content", "has_intro": False, "has_outro": False}
    
    # Check for intro/outro patterns
    first_segment = segments[0] if segments else None
    last_segment = segments[-1] if segments else None
    
    first_text = first_segment.get("transcript", {}).get("full_text", "").lower() if first_segment else ""
    last_text = last_segment.get("transcript", {}).get("full_text", "").lower() if last_segment else ""
    
    intro_indicators = ["hi", "hello", "welcome", "today", "in this video", "let's"]
    outro_indicators = ["thanks", "thank you", "subscribe", "like", "comment", "see you"]
    
    return {
        "structure": "structured" if len(segments) > 3 else "simple",
        "has_intro": any(indicator in first_text for indicator in intro_indicators),
        "has_outro": any(indicator in last_text for indicator in outro_indicators),
        "segment_count": len(segments),
        "average_segment_length": sum(s.get("duration", 0) for s in segments) / len(segments) if segments else 0
    }


def _extract_purpose_indicators(transcript: str, objects: List[str], segments: List[Dict]) -> List[str]:
    """Extract indicators of video purpose."""
    indicators = []
    transcript_lower = transcript.lower()
    
    # Purpose keywords
    purpose_keywords = {
        "educational": ["teach", "learn", "explain", "understand", "how", "why"],
        "entertainment": ["funny", "joke", "laugh", "enjoy", "entertain"],
        "promotional": ["buy", "sale", "discount", "offer", "promo", "deal"],
        "documentary": ["document", "record", "capture", "observe"],
        "social": ["share", "update", "news", "happening", "event"]
    }
    
    for purpose, keywords in purpose_keywords.items():
        if any(keyword in transcript_lower for keyword in keywords):
            indicators.append(purpose)
    
    # Object-based indicators
    if "phone" in objects or "camera" in objects:
        indicators.append("tech_review")
    if "food" in objects:
        indicators.append("food_content")
    if "person" in objects:
        indicators.append("people_focused")
    
    return indicators if indicators else ["general_content"]


def _describe_scene(transcript: str, objects: List[str], duration: float) -> str:
    """Generate a brief scene description."""
    parts = []
    
    if transcript:
        # Get first meaningful sentence
        sentences = transcript.split('.')
        first_sentence = sentences[0].strip() if sentences else ""
        if first_sentence:
            parts.append(f"Features speech: '{first_sentence[:50]}...'")
    
    if objects:
        main_objects = objects[:3]
        parts.append(f"Shows: {', '.join(main_objects)}")
    
    if duration:
        parts.append(f"Duration: {duration:.1f}s")
    
    if not parts:
        return "Visual content with no detected speech or objects"
    
    return " | ".join(parts)


