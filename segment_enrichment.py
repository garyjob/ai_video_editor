#!/usr/bin/env python3
"""
Enrich video segments with scene-change and motion signals for ranking / Grok.

- Scene cuts: FFmpeg lavfi select=gt(scene,threshold) + parse showinfo pts_time.
- Motion: optional OpenCV — mean absolute diff on downsampled grayscale at ~2 fps.

Works alongside video_analyzer.create_segments() output.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SHOWINFO_PTS_RE = re.compile(r"pts_time:([\d.]+)")


def get_scene_change_times(
    video_path: str,
    threshold: float = 0.35,
    max_duration: Optional[float] = 300.0,
) -> List[float]:
    """
    Return timestamps (seconds) where FFmpeg scene score exceeds threshold.
    First frame is not emitted; cuts are boundaries worth noting for editing.
    """
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    path = str(Path(video_path).expanduser())
    vf = f"select='gt(scene\\,{threshold})',showinfo"
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-i", path, "-t", str(max_duration), "-vf", vf, "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        logger.warning("scene detection timed out for %s", path)
        return []
    out = (proc.stderr or "") + (proc.stdout or "")
    times: List[float] = []
    for line in out.splitlines():
        if "showinfo" in line and "pts_time" in line:
            m = SHOWINFO_PTS_RE.search(line)
            if m:
                try:
                    times.append(float(m.group(1)))
                except ValueError:
                    continue
    times.sort()
    return times


def _motion_per_second_cv2(
    video_path: str,
    max_duration: float,
    target_fps: float = 2.0,
) -> Dict[int, float]:
    """Map second index -> mean abs diff vs previous sampled frame (0 if none)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.info("OpenCV unavailable; skipping motion profile")
        return {}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / target_fps)))
    prev_small: Optional[Any] = None
    last_sec: Optional[int] = None
    by_sec: Dict[int, List[float]] = {}

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        t = frame_idx / fps
        if t >= max_duration:
            break
        if frame_idx % step != 0:
            frame_idx += 1
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        sec = int(t)
        if prev_small is not None:
            diff = cv2.absdiff(small, prev_small)
            m = float(diff.mean()) / 255.0
            if sec not in by_sec:
                by_sec[sec] = []
            by_sec[sec].append(m)
        prev_small = small
        last_sec = sec
        frame_idx += 1
    cap.release()

    out: Dict[int, float] = {}
    for sec, vals in by_sec.items():
        out[sec] = sum(vals) / len(vals)
    return out


def normalize_motion(motion_by_sec: Dict[int, float]) -> Dict[int, float]:
    if not motion_by_sec:
        return {}
    vals = list(motion_by_sec.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-6:
        return {k: 0.5 for k in motion_by_sec}
    return {k: (v - lo) / (hi - lo) for k, v in motion_by_sec.items()}


def enrich_segments_visual_dynamics(
    segments: List[Dict[str, Any]],
    scene_times: List[float],
    motion_by_sec_normalized: Dict[int, float],
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Attach scene/motion features and editor_score to each segment (mutates copies).

    editor_score blends existing quality_score with motion and nearby scene activity.
    """
    duration = float(metadata.get("duration") or 0.0)

    def nearest_scene_distance(mid: float) -> float:
        best = 1e9
        for st in scene_times:
            best = min(best, abs(mid - st))
        return best

    enriched: List[Dict[str, Any]] = []
    for seg in segments:
        s = dict(seg)
        tr = s.get("time_range", {})
        start = float(tr.get("start", 0))
        end = float(tr.get("end", start))
        mid = (start + end) / 2.0

        cuts_inside = sum(1 for t in scene_times if start <= t < end)
        dist = nearest_scene_distance(mid)
        scene_proximity = 1.0 / (1.0 + dist)

        mvals = [
            motion_by_sec_normalized.get(sec, 0.0)
            for sec in range(int(start), min(int(end) + 1, int(duration) + 1))
        ]
        motion_mean = sum(mvals) / len(mvals) if mvals else 0.0

        base_q = float(s.get("quality_score", 0.5))
        editor_score = min(
            1.0,
            max(
                0.0,
                0.45 * base_q
                + 0.30 * motion_mean
                + 0.15 * min(1.0, cuts_inside / 2.0)
                + 0.10 * scene_proximity,
            ),
        )

        s["visual_dynamics"] = {
            "scene_cuts_in_range": cuts_inside,
            "nearest_scene_cut_distance_sec": round(dist, 3),
            "motion_mean_normalized": round(motion_mean, 3),
        }
        s["editor_score"] = round(editor_score, 3)
        enriched.append(s)

    return enriched


def enrich_analysis_result(
    analysis: Dict[str, Any],
    progress_callback: Optional[Callable[[str, int], None]] = None,
    scene_threshold: float = 0.35,
    max_duration: float = 300.0,
) -> Dict[str, Any]:
    """
    Enrich a single-video analyze_video() result dict in place.

    Expects keys: path, metadata, segments, file, summary (optional).
    """
    video_path = analysis.get("path")
    if not video_path or not Path(video_path).exists():
        return analysis

    meta = analysis.get("metadata") or {}
    dur = float(meta.get("duration") or 0)
    cap = min(max_duration, dur) if dur else max_duration

    if progress_callback:
        progress_callback("Detecting scene changes (FFmpeg)...", 5)

    scene_times = get_scene_change_times(video_path, threshold=scene_threshold, max_duration=cap)
    analysis["scene_change_times"] = scene_times

    if progress_callback:
        progress_callback("Computing motion profile (OpenCV)...", 30)

    motion_raw = _motion_per_second_cv2(video_path, max_duration=cap)
    motion_norm = normalize_motion(motion_raw)

    segments = analysis.get("segments") or []
    new_segments = enrich_segments_visual_dynamics(segments, scene_times, motion_norm, meta)
    analysis["segments"] = new_segments

    if analysis.get("summary") is not None and new_segments:
        analysis["summary"]["average_editor_score"] = sum(
            s.get("editor_score", 0) for s in new_segments
        ) / len(new_segments)
        analysis["summary"]["scene_cut_count"] = len(scene_times)

    if progress_callback:
        progress_callback("Visual dynamics enrichment complete", 100)

    return analysis


def wrap_multivideo_for_grok(single_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert list of analyze_video outputs to grok_client analysis_data shape."""
    videos = []
    for r in single_results:
        videos.append(
            {
                "file": r.get("file"),
                "path": r.get("path"),
                "metadata": r.get("metadata"),
                "segments": r.get("segments"),
                "summary": r.get("summary"),
                "scene_change_times": r.get("scene_change_times", []),
            }
        )
    return {"videos": videos}
