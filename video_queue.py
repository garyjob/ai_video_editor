#!/usr/bin/env python3
"""
Video processing queue system.

Manages queue of videos to analyze, tracks status, and coordinates background processing.
"""

import os
import uuid
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

try:
    from logger_config import logger
except ImportError:
    import logging
    logger = logging.getLogger('video_queue')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


class VideoStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class QueueItem:
    """Queue item data structure."""
    id: str
    path: str
    filename: str
    status: str
    duration: Optional[float] = None
    progress: int = 0
    current_step: Optional[str] = None
    error: Optional[str] = None
    created_at: str = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    thumbnail_path: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class VideoQueue:
    """Thread-safe video processing queue."""
    
    def __init__(self, max_concurrent: int = 2):
        self.queue: List[QueueItem] = []
        self.results: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.max_concurrent = max_concurrent
        self.processing_count = 0
        self.processor_thread = None
        self.running = False
    
    def add(self, video_paths: List[str]) -> List[str]:
        """
        Add videos to queue.
        
        Args:
            video_paths: List of video file paths
            
        Returns:
            List of queue item IDs
        """
        added_ids = []
        
        logger.info(f"Adding {len(video_paths)} video(s) to queue")
        
        with self.lock:
            for path in video_paths:
                path_obj = Path(path)
                
                # Validate path exists
                if not path_obj.exists():
                    logger.warning(f"Video file not found, skipping: {path}")
                    continue
                
                # Check if already in queue
                if any(item.path == str(path_obj.absolute()) for item in self.queue):
                    logger.info(f"Video already in queue, skipping: {path_obj.name}")
                    continue
                
                logger.debug(f"Processing video: {path_obj.name}")
                
                # Generate thumbnail (relative to uploads folder)
                thumbnail_path = self._generate_thumbnail(path_obj)
                if thumbnail_path:
                    logger.debug(f"Generated thumbnail for {path_obj.name}: {thumbnail_path}")
                else:
                    logger.warning(f"Could not generate thumbnail for {path_obj.name}")
                
                # Create queue item
                item = QueueItem(
                    id=str(uuid.uuid4()),
                    path=str(path_obj.absolute()),
                    filename=path_obj.name,
                    status=VideoStatus.QUEUED.value,
                    thumbnail_path=thumbnail_path
                )
                
                self.queue.append(item)
                added_ids.append(item.id)
                logger.info(f"Added video to queue: {path_obj.name} (ID: {item.id})")
        
        # Start processor if not running
        self._start_processor()
        
        logger.info(f"Successfully added {len(added_ids)} video(s) to queue")
        return added_ids
    
    def _generate_thumbnail(self, video_path: Path) -> Optional[str]:
        """Generate a thumbnail image from video."""
        logger.debug(f"Generating thumbnail for: {video_path.name}")
        try:
            import subprocess
            
            # Use uploads/thumbnails directory (consistent location)
            uploads_dir = video_path.parent
            thumbnails_dir = uploads_dir / 'thumbnails'
            thumbnails_dir.mkdir(exist_ok=True)
            
            # Thumbnail filename
            thumbnail_filename = f"{video_path.stem}_thumb.jpg"
            thumbnail_path = thumbnails_dir / thumbnail_filename
            
            # Skip if already exists
            if thumbnail_path.exists():
                return f"/thumbnails/{thumbnail_filename}"
            
            # Find ffmpeg in PATH or use default location
            import shutil
            ffmpeg_path = shutil.which('ffmpeg') or '/usr/local/bin/ffmpeg'
            
            # Use ffmpeg to extract frame at 1 second (or first frame if video is shorter)
            cmd = [
                ffmpeg_path,
                '-i', str(video_path),
                '-ss', '00:00:01',  # Seek to 1 second
                '-vframes', '1',     # Extract 1 frame
                '-vf', 'scale=320:-1',  # Scale to 320px width, maintain aspect
                '-q:v', '2',         # High quality
                '-y',                # Overwrite if exists
                str(thumbnail_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
                text=True
            )
            
            if result.returncode == 0 and thumbnail_path.exists():
                # Return relative path for web access
                return f"/thumbnails/{thumbnail_filename}"
            else:
                # Fallback: try first frame
                cmd[3] = '00:00:00'
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                if result.returncode == 0 and thumbnail_path.exists():
                    return f"/thumbnails/{thumbnail_filename}"
                
        except Exception as e:
            logger.warning(f"Could not generate thumbnail for {video_path.name}: {e}", exc_info=True)
        
        return None
    
    def remove(self, item_id: str) -> bool:
        """Remove item from queue."""
        with self.lock:
            for i, item in enumerate(self.queue):
                if item.id == item_id:
                    # Only allow removal if queued or error
                    if item.status in [VideoStatus.QUEUED.value, VideoStatus.ERROR.value]:
                        self.queue.pop(i)
                        # Also remove from results
                        self.results.pop(item_id, None)
                        logger.info(f"Removed item from queue: {item_id}")
                        return True
            return False
    
    def reanalyze(self, item_id: str) -> bool:
        """Re-analyze a video by resetting its status and clearing results."""
        with self.lock:
            for item in self.queue:
                if item.id == item_id:
                    # Reset status to queued
                    item.status = VideoStatus.QUEUED.value
                    item.progress = 0
                    item.current_step = None
                    item.error = None
                    item.completed_at = None
                    # Clear previous results
                    self.results.pop(item_id, None)
                    logger.info(f"Reset item for re-analysis: {item_id} ({item.filename})")
                    # Start processor if not running
                    self._start_processor()
                    return True
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status."""
        with self.lock:
            queue_list = [asdict(item) for item in self.queue]
            
            return {
                "queue": queue_list,
                "results": self.results,
                "processing_count": self.processing_count,
                "queue_length": len(self.queue)
            }
    
    def get_result(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis result for an item."""
        with self.lock:
            return self.results.get(item_id)
    
    def _start_processor(self):
        """Start background processor thread."""
        if self.processor_thread is None or not self.processor_thread.is_alive():
            self.running = True
            self.processor_thread = threading.Thread(target=self._process_queue, daemon=True)
            self.processor_thread.start()
    
    def _process_queue(self):
        """Background thread that processes queue."""
        while self.running:
            try:
                # Check for items to process
                item = None
                
                with self.lock:
                    if self.processing_count < self.max_concurrent:
                        # Find next queued item
                        for queued_item in self.queue:
                            if queued_item.status == VideoStatus.QUEUED.value:
                                item = queued_item
                                item.status = VideoStatus.PROCESSING.value
                                item.started_at = datetime.now().isoformat()
                                self.processing_count += 1
                                break
                
                if item:
                    # Process video in background
                    thread = threading.Thread(
                        target=self._analyze_video,
                        args=(item,),
                        daemon=True
                    )
                    thread.start()
                else:
                    # No items to process, sleep
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                time.sleep(1)
    
    def _analyze_video(self, item: QueueItem):
        """Analyze a single video."""
        logger.info(f"Starting analysis for video: {item.filename} (ID: {item.id})")
        try:
            # Import here to avoid circular imports
            from video_analyzer import analyze_video
            
            # Update progress
            self._update_item(item.id, {
                "current_step": "Initializing...",
                "progress": 5
            })
            
            # Analyze video
            def update_progress(step: str, progress: int):
                logger.debug(f"Progress update for {item.filename}: {step} ({progress}%)")
                self._update_item(item.id, {"current_step": step, "progress": progress})
            
            result = analyze_video(item.path, progress_callback=update_progress)
            logger.info(f"Analysis complete for {item.filename}: {len(result.get('segments', []))} segments")
            
            # Store result
            with self.lock:
                self.results[item.id] = result
                # Update item status
                for queue_item in self.queue:
                    if queue_item.id == item.id:
                        queue_item.status = VideoStatus.COMPLETE.value
                        queue_item.completed_at = datetime.now().isoformat()
                        queue_item.progress = 100
                        queue_item.current_step = "Complete"
                        if "metadata" in result:
                            queue_item.duration = result["metadata"].get("duration")
                        break
                self.processing_count -= 1
                
        except Exception as e:
            # Handle error
            logger.error(f"Error analyzing video {item.filename} (ID: {item.id}): {e}", exc_info=True)
            with self.lock:
                for queue_item in self.queue:
                    if queue_item.id == item.id:
                        queue_item.status = VideoStatus.ERROR.value
                        queue_item.error = str(e)
                        queue_item.progress = 0
                        logger.error(f"Marked video as error: {item.filename} - {e}")
                        break
                self.processing_count -= 1
    
    def _update_item(self, item_id: str, updates: Dict[str, Any]):
        """Update queue item."""
        with self.lock:
            for item in self.queue:
                if item.id == item_id:
                    for key, value in updates.items():
                        setattr(item, key, value)
                    break


# Global queue instance
_queue_instance: Optional[VideoQueue] = None


def get_queue() -> VideoQueue:
    """Get global queue instance."""
    global _queue_instance
    if _queue_instance is None:
        max_concurrent = int(os.environ.get("MAX_CONCURRENT_ANALYSIS", 2))
        _queue_instance = VideoQueue(max_concurrent=max_concurrent)
    return _queue_instance

