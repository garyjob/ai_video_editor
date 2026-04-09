#!/usr/bin/env python3
"""
Disk cache for per-clip analyze_video() results.

Skip Whisper / YOLO / enrichment when the same file is seen again with the same
size, mtime, enrichment flag, and EXTRACTION_PIPELINE_VERSION.

Bump EXTRACTION_PIPELINE_VERSION whenever segmentation, Whisper usage, YOLO
sampling, or segment_enrichment / editor_score logic changes materially.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Increment when extraction outputs would differ for the same input file.
EXTRACTION_PIPELINE_VERSION = 1


def _stat_fingerprint(path: Path) -> tuple[int, int]:
    st = path.stat()
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return int(st.st_size), int(mtime_ns)


def cache_json_path(project_root: Path, video_path: Path, enrich_visual: bool) -> Path:
    """Deterministic cache filename under uploads/analysis_cache/."""
    resolved = str(video_path.resolve())
    size, mtime_ns = _stat_fingerprint(video_path)
    blob = (
        f"{resolved}|{size}|{mtime_ns}|{int(enrich_visual)}|{EXTRACTION_PIPELINE_VERSION}"
    ).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    return project_root / "uploads" / "analysis_cache" / f"{digest}.json"


def load_cached_analysis(
    cache_path: Path,
    video_path: Path,
    enrich_visual: bool,
) -> Optional[Dict[str, Any]]:
    """Return analysis dict if cache is valid; otherwise None."""
    if not cache_path.is_file():
        return None
    if not video_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    meta = payload.get("_meta")
    analysis = payload.get("analysis")
    if not isinstance(meta, dict) or not isinstance(analysis, dict):
        return None

    if int(meta.get("pipeline_version", -1)) != EXTRACTION_PIPELINE_VERSION:
        return None
    if bool(meta.get("enrich_visual_dynamics")) != bool(enrich_visual):
        return None
    if str(meta.get("path_resolved", "")) != str(video_path.resolve()):
        return None

    size, mtime_ns = _stat_fingerprint(video_path)
    if int(meta.get("size", -1)) != size or int(meta.get("mtime_ns", -1)) != mtime_ns:
        return None

    return analysis


def save_cached_analysis(
    cache_path: Path,
    video_path: Path,
    enrich_visual: bool,
    analysis: Dict[str, Any],
) -> None:
    size, mtime_ns = _stat_fingerprint(video_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "pipeline_version": EXTRACTION_PIPELINE_VERSION,
            "path_resolved": str(video_path.resolve()),
            "size": size,
            "mtime_ns": mtime_ns,
            "enrich_visual_dynamics": bool(enrich_visual),
        },
        "analysis": analysis,
    }
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(cache_path)
