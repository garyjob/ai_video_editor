# Segment ranking pipeline: transcript + motion + scene-change + Grok

This describes how **`video_editor`** combines signals so you can pick the best moments for Shorts (e.g. ~30 s), including the **full-frame letterbox** export you preferred.

## 1. What each layer does

| Signal | Source | Role |
|--------|--------|------|
| **Transcript** | Whisper (`video_analyzer.transcribe_with_whisper`) | Word/segment timing, “what was said”, confidence feeds `quality_score`. |
| **Objects** | YOLO (`detect_objects_with_yolo`) | Rough “what’s on screen” for summaries and Grok context. |
| **Segments** | `create_segments` | 5–10 s-ish units merging transcript + detections. |
| **Scene changes** | FFmpeg `select=gt(scene,t)` (`segment_enrichment.get_scene_change_times`) | Cut-like boundaries; boosts segments with real visual change. |
| **Motion** | OpenCV frame diffs ~2 fps (`_motion_per_second_cv2`) | Favors active shots (stirring, movement); optional if `cv2` missing. |
| **editor_score** | `enrich_segments_visual_dynamics` | Single 0–1 blend of speech quality, motion, scene cuts / proximity. |
| **Grok ranking** | `grok_client.analyze_video_segments` | Reads segment lines (including `editor_score`) and returns `editing_plan` JSON. |

## 2. Turning enrichment on

**Option A — environment**

```bash
export VIDEO_ENRICH=1
python app.py  # or your script calling analyze_video
```

**Option B — argument**

```python
from video_analyzer import analyze_video

result = analyze_video("/path/to/clip.MOV", enrich_visual_dynamics=True)
```

Enriched segments include:

- `editor_score`
- `visual_dynamics`: `scene_cuts_in_range`, `nearest_scene_cut_distance_sec`, `motion_mean_normalized`

`result["scene_change_times"]` lists FFmpeg-detected cut times (seconds).

## 3. Multi-clip folder → Grok

```python
from video_analyzer import analyze_video
from segment_enrichment import wrap_multivideo_for_grok
from grok_client import analyze_video_segments

paths = [...]  # list of .MOV
rows = []
for p in paths:
    rows.append(analyze_video(p, enrich_visual_dynamics=True))

bundle = wrap_multivideo_for_grok(rows)
plan = analyze_video_segments(
    bundle,
    target_duration_min=25,
    target_duration_max=35,
    user_direction="Roasting chocolate at home with Mulan; warm, cozy, not corporate.",
)
# plan["editing_plan"] → selected_segments, sequence, trim_suggestions
```

Then feed `plan` + file path map into `video_editor.generate_video_from_plan`, and apply your **letterbox 9:16** FFmpeg filter on each extracted segment (same as `mulan_roast_30s` v2).

## 4. Tuning

- **Scene sensitivity**: lower FFmpeg threshold → more cuts (default `0.35` in `get_scene_change_times`).
- **Motion**: increase `target_fps` in `_motion_per_second_cv2` for noisier kitchen footage (costs CPU).
- **Weights**: edit `enrich_segments_visual_dynamics` formula if you want “motion-first” vs “speech-first” Shorts.
- **No OpenCV**: motion map is empty; ranking falls back to transcript + scene cuts only.

## 5. Honest limits

- **No pet/person-centric auto-framing** — that’s a separate model(s) step.
- **Grok** does not “watch” pixels; it ranks from **text summaries** you send — good segment **summaries/transcripts** matter.
- Long clips still respect analyzer **duration cap** (default 300 s analyzed unless you change it).

---

*See also: `SHORT_VIDEO_FORMAT.md`, `ANALYSIS_FORMAT_PROPOSAL.md`, `segment_enrichment.py`, `grok_client.py`.*
