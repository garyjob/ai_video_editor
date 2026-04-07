#!/usr/bin/env python3
"""
Video editing module to generate final video from Grok's editing plan.

Uses moviepy to cut, trim, and combine video segments according to Grok's instructions.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import subprocess
import shutil

try:
    from logger_config import logger
except ImportError:
    import logging
    logger = logging.getLogger('video_editor')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def generate_video_from_plan(
    editing_plan: Dict[str, Any],
    source_videos: Dict[str, str],  # Maps video filenames to file paths
    output_path: Optional[str] = None,
    progress_callback: Optional[Any] = None
) -> str:
    """
    Generate final video from Grok's editing plan.
    
    Args:
        editing_plan: Grok's editing plan with selected segments, trims, sequence, etc.
        source_videos: Dict mapping video filenames to their file paths
        output_path: Optional output path (default: generates in uploads/generated/)
        progress_callback: Optional callback for progress updates
    
    Returns:
        Path to generated video file
    """
    try:
        from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip
    except ImportError:
        logger.error("moviepy not installed. Install with: pip install moviepy")
        raise ImportError("moviepy is required for video editing")
    
    if progress_callback:
        progress_callback("Loading video files...", 10)
    
    editing_info = editing_plan.get('editing_plan', {})
    selected_segments = editing_info.get('selected_segments', [])
    sequence = editing_info.get('sequence', [])
    transitions = editing_info.get('transitions', [])
    
    if not selected_segments:
        raise ValueError("No segments selected in editing plan")
    
    # Create output directory
    if output_path is None:
        output_dir = Path(__file__).parent / 'uploads' / 'generated'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / 'generated_video.mp4')
    else:
        output_path = str(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Generating video from {len(selected_segments)} segments")
    
    # Load and prepare video clips
    clips = []
    segment_map = {seg.get('segment_id'): seg for seg in selected_segments}
    
    if progress_callback:
        progress_callback(f"Processing {len(sequence)} segments...", 20)
    
    for i, segment_id in enumerate(sequence):
        segment = segment_map.get(segment_id)
        if not segment:
            logger.warning(f"Segment {segment_id} not found in selected segments, skipping")
            continue
        
        video_file = segment.get('video_file')
        if not video_file:
            logger.warning(f"Segment {segment_id} missing video_file, skipping")
            continue
        
        # Get source video path
        source_path = source_videos.get(video_file)
        if not source_path or not Path(source_path).exists():
            logger.warning(f"Source video not found: {video_file} (path: {source_path})")
            continue
        
        time_range = segment.get('time_range', {})
        start_time = time_range.get('start', 0)
        end_time = time_range.get('end', start_time + 5)  # Default 5 seconds if missing
        
        # Check for trim suggestions
        trim_suggestions = editing_info.get('trim_suggestions', [])
        trim_info = next((t for t in trim_suggestions if t.get('segment_id') == segment_id), None)
        if trim_info:
            trim_from = trim_info.get('trim_from', start_time)
            trim_to = trim_info.get('trim_to', end_time)
            start_time = max(start_time, trim_from)
            end_time = min(end_time, trim_to)
        
        try:
            if progress_callback:
                progress = 20 + int((i / len(sequence)) * 60)
                progress_callback(f"Loading segment {i+1}/{len(sequence)}: {video_file} ({start_time:.1f}s-{end_time:.1f}s)", progress)
            
            # Load video clip
            clip = VideoFileClip(source_path)
            
            # Extract segment
            if end_time > clip.duration:
                end_time = clip.duration
            if start_time < 0:
                start_time = 0
            if start_time >= end_time:
                logger.warning(f"Invalid time range for segment {segment_id}, skipping")
                clip.close()
                continue
            
            segment_clip = clip.subclip(start_time, end_time)
            
            # Apply transitions if specified
            transition = next((t for t in transitions if t.get('to_segment') == segment_id), None)
            if transition and transition.get('type') == 'fade' and i > 0:
                fade_duration = min(transition.get('duration', 0.5), segment_clip.duration / 2)
                segment_clip = segment_clip.fadein(fade_duration)
            
            clips.append(segment_clip)
            clip.close()  # Close original to free memory
            
        except Exception as e:
            logger.error(f"Error processing segment {segment_id}: {e}", exc_info=True)
            continue
    
    if not clips:
        raise ValueError("No valid video clips were created from the editing plan")
    
    if progress_callback:
        progress_callback("Concatenating video segments...", 85)
    
    # Concatenate clips
    logger.info(f"Concatenating {len(clips)} video clips")
    final_clip = concatenate_videoclips(clips, method="compose")
    
    # Ensure vertical format (9:16) for YouTube Shorts
    target_width = 1080
    target_height = 1920
    target_aspect = target_width / target_height
    
    if progress_callback:
        progress_callback("Formatting for YouTube Shorts (9:16)...", 90)
    
    current_width, current_height = final_clip.size
    current_aspect = current_width / current_height
    
    if abs(current_aspect - target_aspect) > 0.01:  # If aspect ratio differs significantly
        # Resize to fit 9:16, cropping if necessary
        if current_aspect > target_aspect:
            # Video is wider, crop sides
            new_width = int(current_height * target_aspect)
            final_clip = final_clip.crop(x_center=current_width/2, width=new_width)
        else:
            # Video is taller, crop top/bottom
            new_height = int(current_width / target_aspect)
            final_clip = final_clip.crop(y_center=current_height/2, height=new_height)
    
    # Resize to target resolution
    final_clip = final_clip.resize((target_width, target_height))
    
    if progress_callback:
        progress_callback("Rendering final video...", 95)
    
    # Write final video
    logger.info(f"Rendering video to: {output_path}")
    final_clip.write_videofile(
        output_path,
        codec='libx264',
        audio_codec='aac',
        fps=30,
        preset='medium',
        bitrate='8000k',
        logger=None  # Suppress moviepy's verbose logging
    )
    
    # Clean up
    final_clip.close()
    for clip in clips:
        clip.close()
    
    if progress_callback:
        progress_callback("Video generation complete!", 100)
    
    logger.info(f"Video generated successfully: {output_path}")
    return output_path

