# Video Analysis Format Proposal

## Overview

Format for storing video analysis results that is:
1. **Human-readable** - Easy to view and verify
2. **Grok-friendly** - Easy for LLM to understand and suggest edits
3. **Edit-ready** - Easy for app to apply Grok's suggestions

## Video Constraints

- **Input videos**: Up to 2 minutes each
- **Output video**: 15 seconds to 2 minutes (target duration)
- **Goal**: Cut/stitch multiple clips into coherent short video
- **Segment size**: 5-10 seconds (sentence/thought breaks) for granular editing

## Recommended Format: Structured JSON

### Structure

```json
{
  "analysis_id": "analysis_20240104_103000",
  "timestamp": "2024-01-04T10:30:00Z",
  "videos": [
    {
      "file": "video1.mp4",
      "path": "/Users/garyjob/Downloads/video1.mp4",
      "metadata": {
        "duration": 120.5,
        "fps": 30,
        "resolution": "1920x1080",
        "codec": "h264",
        "file_size_mb": 45.2
      },
      "segments": [
        {
          "id": "video1_seg_001",
          "time_range": {
            "start": 0.0,
            "end": 15.3
          },
          "transcript": {
            "full_text": "Hello, welcome to our channel. Today we'll discuss video editing.",
            "words": [
              {"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.98},
              {"word": "welcome", "start": 0.5, "end": 1.2, "confidence": 0.95},
              {"word": "to", "start": 1.2, "end": 1.4, "confidence": 0.99}
            ],
            "language": "en",
            "speaker_count": 1
          },
          "objects": [
            {
              "name": "person",
              "confidence": 0.95,
              "time": 2.5,
              "bbox": {"x": 100, "y": 200, "width": 300, "height": 400},
              "duration": 12.0
            },
            {
              "name": "laptop",
              "confidence": 0.87,
              "time": 3.0,
              "bbox": {"x": 150, "y": 250, "width": 350, "height": 450},
              "duration": 10.5
            }
          ],
          "summary": "Introduction and greeting. Speaker at desk with laptop visible.",
          "key_moments": ["greeting", "introduction"],
          "quality_score": 0.85
        },
        {
          "id": "video1_seg_002",
          "time_range": {
            "start": 15.3,
            "end": 42.1
          },
          "transcript": {
            "full_text": "Let's start with the basics of video editing...",
            "words": [...]
          },
          "objects": [...],
          "summary": "Tutorial begins. Demonstrates video editing basics.",
          "key_moments": ["tutorial_start", "demonstration"],
          "quality_score": 0.92
        }
      ],
      "summary": {
        "main_topics": ["introduction", "video_editing_tutorial", "demonstration"],
        "total_segments": 8,
        "total_duration": 120.5,
        "object_types": ["person", "laptop", "coffee", "phone"],
        "speaker_count": 1,
        "language": "en"
      }
    },
    {
      "file": "video2.mp4",
      "path": "/Users/garyjob/Downloads/video2.mp4",
      "metadata": {...},
      "segments": [...],
      "summary": {...}
    }
  ],
  "global_summary": {
    "total_videos": 2,
    "total_duration": 245.7,
    "all_topics": ["introduction", "tutorial", "demo"],
    "all_objects": ["person", "laptop", "coffee", "phone"]
  }
}
```

## Why This Format?

### For Human Review
- ✅ Segments with clear time ranges (0:00 - 0:15)
- ✅ Full transcript text (readable)
- ✅ Object list with confidence scores
- ✅ Summary per segment (quick overview)
- ✅ Can generate markdown preview for display

### For Grok API
- ✅ Structured JSON (easy to parse)
- ✅ Clear segments as natural editing units
- ✅ Precise timestamps for references
- ✅ Rich context (transcript + objects + summaries)
- ✅ Can create natural language prompts from structure

### For Video Editing
- ✅ Precise timestamps (cut points: start/end)
- ✅ Segment IDs (reference system)
- ✅ Time ranges (for clip extraction)
- ✅ Ordered structure (sequence)
- ✅ All videos in one structure (for stitching)

## Grok Response Format

```json
{
  "editing_plan": {
    "segments_to_keep": [
      {"segment_id": "video1_seg_001", "reason": "Good introduction"},
      {"segment_id": "video1_seg_003", "reason": "Key tutorial content"},
      {"segment_id": "video2_seg_002", "reason": "Important demonstration"}
    ],
    "segments_to_cut": [
      {"segment_id": "video1_seg_002", "reason": "Repetitive content"},
      {"segment_id": "video2_seg_005", "reason": "Off-topic tangent"}
    ],
    "sequence": [
      "video1_seg_001",
      "video1_seg_003",
      "video2_seg_002"
    ],
    "transitions": [
      {
        "from_segment": "video1_seg_001",
        "to_segment": "video1_seg_003",
        "type": "cut",
        "reason": "Seamless transition"
      },
      {
        "from_segment": "video1_seg_003",
        "to_segment": "video2_seg_002",
        "type": "fade",
        "duration": 0.5,
        "reason": "Smooth transition between videos"
      }
    ]
  },
  "metadata": {
    "title": "Video Editing Basics Tutorial",
    "description": "Learn the fundamentals of video editing with this comprehensive tutorial covering key techniques and demonstrations.",
    "tags": ["tutorial", "video editing", "how-to", "beginners"],
    "category": "Education"
  }
}
```

## Implementation Benefits

1. **Segments as building blocks** - Natural units for cutting/stitching
2. **Precise timestamps** - Exact cut points for video editing
3. **Rich context** - Transcript + objects + summaries for Grok
4. **Human-readable** - Can generate markdown/text previews
5. **Edit-ready** - Structured format maps directly to editing operations

## File Selection Approach

Since videos are local (Downloads folder):

1. **Path Input**: User enters file paths directly
2. **Validation**: Backend checks paths exist and are valid videos
3. **Analysis**: Read videos from paths (no upload)
4. **Storage**: Save analysis JSON alongside videos or in analysis folder

Example:
- User inputs: `/Users/garyjob/Downloads/video1.mp4`
- Backend validates path exists
- Analyzes video directly from path
- Saves analysis: `/Users/garyjob/Downloads/video1_analysis.json`

