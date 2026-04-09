#!/usr/bin/env python3
"""
Grok API client for video editing suggestions.

Provides interface to Grok API for analyzing video segments and generating
editing suggestions, titles, descriptions, and tags.
"""

import os
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any


GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-3"


def get_grok_api_key() -> Optional[str]:
    """Get Grok API key from environment variables."""
    # Check environment variable first
    api_key = os.environ.get("GROK_API_KEY")
    if api_key:
        return api_key
    
    # Check .env file
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)
            api_key = os.environ.get("GROK_API_KEY")
            if api_key:
                return api_key
    except ImportError:
        pass
    
    return None


def analyze_video_segments(
    analysis_data: Dict[str, Any], 
    target_duration_min: int = 15, 
    target_duration_max: int = 60,
    user_direction: Optional[str] = None,
    additional_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send video analysis to Grok and get editing suggestions.
    
    Args:
        analysis_data: Video analysis data (from video_analyzer.py)
        target_duration_min: Minimum output duration in seconds (default: 15)
        target_duration_max: Maximum output duration in seconds (default: 60)
        user_direction: User's direction/instructions for the video (optional)
        additional_context: Additional context from user (optional)
    
    Returns:
        Dict with editing plan and metadata
    """
    api_key = get_grok_api_key()
    if not api_key:
        raise ValueError("GROK_API_KEY not configured. Set environment variable or .env file.")
    
    # Build prompt from analysis data
    prompt = build_grok_prompt(analysis_data, target_duration_min, target_duration_max, user_direction, additional_context)
    
    # Prepare API request
    payload = {
        "model": GROK_MODEL,
        "temperature": 0.7,
        "messages": [
            {
                "role": "system",
                "content": system_prompt()
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.post(
            GROK_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if not response.ok:
            error_msg = f"Grok API error: {response.status_code} - {response.text}"
            raise Exception(error_msg)
        
        result = response.json()
        
        # Extract response content
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON response
            try:
                # Try to extract JSON from markdown code blocks if present
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                
                editing_plan = json.loads(content)
                return editing_plan
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse Grok response as JSON: {e}\nResponse: {content}")
        else:
            raise Exception(f"Unexpected response format: {result}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Grok API request failed: {e}")


def system_prompt() -> str:
    """System prompt for Grok."""
    return """You are an expert video editor helping create YouTube Shorts / Instagram Reels (vertical 9:16, ~15-60 seconds).
Your task is to analyze video segments and create an editing plan that:
1. Selects segments that feel DIVERSE: avoid repeating the same activity/beat (e.g. many nearly identical "roast/stir" shots). Prefer a mix of process, reactions, sensory moments, and payoffs across clips.
2. Favors moments viewers actually share: genuinely FUNNY (surprise, playful banter, relatable mishap) or AWE / DELIGHT (wonder, beauty, first taste, "wow" reactions, satisfying milestones).
3. Suggests precise cut points and transitions
4. Generates compelling title, description, and tags optimized for Shorts/Reels
5. Ensures the final runtime fits the target duration (15-60 seconds)

Respond ONLY with valid JSON in this exact format:
{
  "editing_plan": {
    "target_duration_seconds": <target duration>,
    "selected_segments": [
      {
        "segment_id": "<segment_id>",
        "video_file": "<filename>",
        "time_range": {"start": <seconds>, "end": <seconds>},
        "keep_reason": "<brief reason>"
      }
    ],
    "total_duration": <total seconds>,
    "trim_suggestions": [
      {
        "segment_id": "<segment_id>",
        "trim_from": <seconds>,
        "trim_to": <seconds>,
        "reason": "<reason for trim>"
      }
    ],
    "final_duration": <final duration in seconds>,
    "sequence": ["<segment_id>", ...],
    "transitions": [
      {
        "from_segment": "<segment_id>",
        "to_segment": "<segment_id>",
        "type": "cut" | "fade" | "dissolve",
        "duration": <seconds>
      }
    ]
  },
  "metadata": {
    "title": "<YouTube Short title (max 100 chars)>",
    "description": "<Description (max 5000 chars)>",
    "tags": ["tag1", "tag2", ...],
    "category": "Education" | "Entertainment" | "Howto" | "Music" | "News" | "People" | "Sports" | "Tech" | "Travel"
  }
}"""


def build_grok_prompt(
    analysis_data: Dict[str, Any], 
    target_duration_min: int, 
    target_duration_max: int,
    user_direction: Optional[str] = None,
    additional_context: Optional[str] = None
) -> str:
    """Build prompt for Grok from analysis data."""
    
    prompt_parts = [
        f"You are analyzing video content to create a YouTube Short (vertical format, {target_duration_min}-{target_duration_max} seconds).",
        ""
    ]
    
    # Add user direction if provided
    if user_direction and user_direction.strip():
        prompt_parts.extend([
            "USER DIRECTION & INSTRUCTIONS:",
            "=" * 60,
            user_direction.strip(),
            "",
            "IMPORTANT: Follow the user's direction above when creating the editing plan.",
            ""
        ])
    
    # Add additional context if provided
    if additional_context and additional_context.strip():
        prompt_parts.extend([
            "ADDITIONAL CONTEXT:",
            "=" * 60,
            additional_context.strip(),
            ""
        ])
    
    prompt_parts.extend([
        "Video Analysis Data:",
        "=" * 60,
        ""
    ])
    
    # Add video summaries
    for video in analysis_data.get("videos", []):
        video_summary = video.get("summary", {})
        segments = video.get("segments", [])
        
        prompt_parts.append(f"Video: {video.get('file', 'unknown')}")
        prompt_parts.append(f"Duration: {video.get('metadata', {}).get('duration', 0):.1f} seconds")
        prompt_parts.append(f"Total Segments: {len(segments)}")
        sct = video.get("scene_change_times") or []
        if sct:
            prompt_parts.append(f"Scene-change cuts detected (FFmpeg): {len(sct)}")
        prompt_parts.append(f"Main Topics: {', '.join(video_summary.get('main_topics', []))}")
        prompt_parts.append("")
        
        # Add segment details (limited to avoid token limits)
        prompt_parts.append("Key Segments:")
        for i, segment in enumerate(segments[:28]):  # Wider coverage per video for diversity
            seg_id = segment.get("id", f"seg_{i}")
            time_range = segment.get("time_range", {})
            transcript = segment.get("transcript", {}).get("full_text", "")
            summary = segment.get("summary", "")
            priority = segment.get("priority", "medium")
            quality = segment.get("quality_score", 0.5)
            editor = segment.get("editor_score")
            vd = segment.get("visual_dynamics") or {}
            
            prompt_parts.append(f"\n{seg_id}:")
            prompt_parts.append(f"  Time: {time_range.get('start', 0):.1f}s - {time_range.get('end', 0):.1f}s ({time_range.get('end', 0) - time_range.get('start', 0):.1f}s)")
            prompt_parts.append(f"  Transcript: {transcript[:200]}{'...' if len(transcript) > 200 else ''}")
            prompt_parts.append(f"  Summary: {summary}")
            prompt_parts.append(f"  Priority: {priority}, Quality (speech): {quality:.2f}")
            if editor is not None:
                prompt_parts.append(
                    f"  Editor score (speech+motion+scene): {float(editor):.2f}; "
                    f"motion_norm_mean={vd.get('motion_mean_normalized', 'n/a')}, "
                    f"scene_cuts_in_range={vd.get('scene_cuts_in_range', 0)}"
                )
        
        if len(segments) > 28:
            prompt_parts.append(f"\n  ... ({len(segments) - 28} more segments)")
        prompt_parts.append("")
    
    # Add task instructions
    prompt_parts.extend([
        "=" * 60,
        "",
        f"Task: Create an editing plan to produce a vertical Short/Reel ({target_duration_min}-{target_duration_max} seconds) by:",
        "1. Selecting segments from ALL available videos — vary activities (hands-on, talking/reactions, tasting/sipping, milestones). Do NOT select only one repetitive stage.",
        "2. Ordering clips for narrative + emotional payoff (setup → interesting middle → satisfying or funny end when possible)",
        "3. Suggesting precise cut points if needed to fit duration",
        "4. Suggesting transitions between segments",
        "5. Generating title, description, and tags that lean humorous OR awe-inspiring where faithful to the footage",
        "",
        "Prioritize segments with strong transcripts that sound funny, surprising, or amazed; or strong visual payoffs. "
        "Use editor_score and motion as tie-breakers, not the only signal. "
        "If two segments are similar in topic and framing, pick only the stronger one — diversify.",
        "",
        "Respond with JSON in the exact format specified in the system prompt."
    ])
    
    return "\n".join(prompt_parts)


