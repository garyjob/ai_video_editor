# Analysis Format for Short Videos (2 minutes max)

## Video Constraints

- **Input videos**: Up to 2 minutes each
- **Output video**: 15 seconds to 2 minutes (target duration)
- **Goal**: Cut/stitch multiple short clips into coherent final video

## Segment Strategy

### Segment Size: 5-10 seconds
- Natural sentence/thought breaks
- 2-minute video → ~12-24 segments
- Allows precise cuts for short output videos
- Word-level timestamps essential for precision

### Why Smaller Segments?
1. **Precise cuts** - Need exact control for 15s-2min output
2. **Quality selection** - Smaller units = better selection of best moments
3. **Grok analysis** - Easier to rank/select smaller segments
4. **Editing flexibility** - More options for combining segments

## Recommended Format Structure

```json
{
  "analysis_id": "analysis_20240104_103000",
  "timestamp": "2024-01-04T10:30:00Z",
  "target_duration": {
    "min_seconds": 15,
    "max_seconds": 120,
    "target_seconds": 90
  },
  "videos": [
    {
      "file": "video1.mp4",
      "path": "/Users/garyjob/Downloads/video1.mp4",
      "metadata": {
        "duration": 120.0,
        "fps": 30,
        "resolution": "1920x1080"
      },
      "segments": [
        {
          "id": "video1_seg_001",
          "time_range": {
            "start": 0.0,
            "end": 8.5
          },
          "duration": 8.5,
          "transcript": {
            "full_text": "Hello, welcome to our channel. Today we'll discuss video editing.",
            "words": [
              {"word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.98},
              {"word": "welcome", "start": 0.5, "end": 1.2, "confidence": 0.95}
            ],
            "language": "en"
          },
          "objects": [
            {
              "name": "person",
              "confidence": 0.95,
              "time": 2.5,
              "bbox": {"x": 100, "y": 200, "width": 300, "height": 400}
            }
          ],
          "priority": "high",
          "quality_score": 0.92,
          "summary": "Introduction and greeting. Speaker visible.",
          "key_moments": ["greeting", "introduction"]
        },
        {
          "id": "video1_seg_002",
          "time_range": {
            "start": 8.5,
            "end": 15.2
          },
          "duration": 6.7,
          "transcript": {...},
          "objects": [...],
          "priority": "medium",
          "quality_score": 0.78,
          "summary": "Transition to main topic."
        }
      ],
      "total_segments": 14,
      "key_moments": [
        {
          "segment_id": "video1_seg_001",
          "time": 0.0,
          "importance": "high",
          "reason": "Strong introduction"
        },
        {
          "segment_id": "video1_seg_007",
          "time": 45.3,
          "importance": "high",
          "reason": "Key demonstration"
        }
      ],
      "summary": {
        "main_topics": ["introduction", "tutorial"],
        "total_duration": 120.0,
        "segment_count": 14,
        "average_segment_duration": 8.6
      }
    }
  ],
  "global_summary": {
    "total_videos": 3,
    "total_duration": 360.0,
    "total_segments": 42,
    "key_moments_count": 8
  }
}
```

## Key Features for Short Videos

### 1. Priority Scoring
- Each segment has `priority` (high/medium/low)
- Helps Grok identify best segments quickly
- Based on transcript content + object presence

### 2. Quality Score
- `quality_score` (0-1) per segment
- Factors: audio clarity, visual quality, object detection confidence
- Helps rank segments for selection

### 3. Key Moments
- Flagged segments with high importance
- Helps Grok prioritize what to keep
- Essential for creating 15s-2min highlight reel

### 4. Precise Timestamps
- Word-level timestamps for exact cuts
- Segment boundaries at natural breaks
- Allows precise trimming for duration target

## Grok Editing Response Format

```json
{
  "editing_plan": {
    "target_duration_seconds": 90,
    "selected_segments": [
      {
        "segment_id": "video1_seg_001",
        "video_file": "video1.mp4",
        "time_range": {"start": 0.0, "end": 8.5},
        "keep_reason": "Strong introduction"
      },
      {
        "segment_id": "video2_seg_005",
        "video_file": "video2.mp4",
        "time_range": {"start": 12.3, "end": 22.1},
        "keep_reason": "Key demonstration"
      },
      {
        "segment_id": "video1_seg_007",
        "video_file": "video1.mp4",
        "time_range": {"start": 45.3, "end": 52.0},
        "keep_reason": "Important conclusion"
      }
    ],
    "total_duration": 95.0,
    "trim_suggestions": [
      {
        "segment_id": "video1_seg_001",
        "trim_from": 6.0,
        "trim_to": 8.5,
        "reason": "Cut intro filler, keep core message"
      }
    ],
    "final_duration": 92.0,
    "sequence": ["video1_seg_001", "video2_seg_005", "video1_seg_007"],
    "transitions": [
      {
        "from_segment": "video1_seg_001",
        "to_segment": "video2_seg_005",
        "type": "fade",
        "duration": 0.5
      }
    ]
  },
  "metadata": {
    "title": "Video Editing Basics - Quick Tutorial",
    "description": "Learn video editing fundamentals in this concise tutorial...",
    "tags": ["tutorial", "video editing", "quick guide"],
    "category": "Education"
  }
}
```

## Processing Considerations

### Analysis Speed
- 2-minute videos process quickly (Whisper: ~30-60 seconds)
- YOLO object detection: ~10-20 seconds per video
- Multiple videos can process in parallel

### Storage
- Analysis JSON: ~50-200KB per video
- Small storage footprint
- Can cache analysis for reuse

### Editing Precision
- Word-level timestamps enable frame-accurate cuts
- Small segments allow fine-grained selection
- Easy to trim segments to fit duration target


