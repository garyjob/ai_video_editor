#!/usr/bin/env python3
"""
Remove long inter-word / leading silence inside a clip window using Whisper word timestamps.

Conservative: only gaps in [min_pause, max_pause]; cap total removed fraction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _words_in_range(
    analysis: Dict[str, Any], spec_start: float, spec_end: float
) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for seg in analysis.get("segments") or []:
        tr = seg.get("transcript") or {}
        for w in tr.get("words") or []:
            if not isinstance(w, dict):
                continue
            try:
                ws = float(w.get("start", 0))
                we = float(w.get("end", 0))
            except (TypeError, ValueError):
                continue
            if we <= spec_start or ws >= spec_end:
                continue
            a = max(ws, spec_start)
            b = min(we, spec_end)
            if b - a > 0.02:
                out.append((a, b))
    out.sort(key=lambda x: x[0])
    return out


def _merge_close(intervals: List[Tuple[float, float]], bridge: float) -> List[Tuple[float, float]]:
    if not intervals:
        return []
    merged: List[Tuple[float, float]] = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = merged[-1]
        if s <= pe + bridge:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def local_keep_intervals_simple(
    analysis: Dict[str, Any],
    spec_start: float,
    spec_end: float,
    *,
    min_pause_remove: float = 0.78,
    max_pause_remove: float = 2.85,
    bridge_same_utterance: float = 0.22,
    max_remove_fraction: float = 0.24,
) -> List[Tuple[float, float]]:
    """
    Return list of (local_start, local_end) relative to spec_start for ffmpeg trim/concat.
    Single [(0, dur)] if nothing to tighten or words missing.
    """
    dur = max(0.0, spec_end - spec_start)
    if dur < 0.12:
        return [(0.0, dur)]
    words = _words_in_range(analysis, spec_start, spec_end)
    if len(words) < 2:
        return [(0.0, dur)]
    blocks = _merge_close(words, bridge_same_utterance)
    pieces: List[Tuple[float, float]] = []
    prev_end: Optional[float] = None
    max_remove = dur * max_remove_fraction
    removed = 0.0

    for s, e in blocks:
        s = max(s, spec_start)
        e = min(e, spec_end)
        if e <= s + 0.02:
            continue
        if prev_end is None:
            lead = s - spec_start
            if min_pause_remove <= lead <= max_pause_remove:
                removed += lead
                pieces.append((s, e))
            else:
                pieces.append((spec_start, e))
            prev_end = e
            continue
        gap = s - prev_end
        if min_pause_remove <= gap <= max_pause_remove:
            need = gap
            if removed + need > max_remove:
                if pieces:
                    ps, pe = pieces[-1]
                    pieces[-1] = (ps, max(pe, e))
            else:
                removed += need
                pieces.append((s, e))
        else:
            if gap <= bridge_same_utterance and pieces:
                ps, pe = pieces[-1]
                pieces[-1] = (ps, max(pe, e))
            else:
                pieces.append((s, e))
        prev_end = e

    if not pieces:
        return [(0.0, dur)]
    locs: List[Tuple[float, float]] = []
    for a, b in pieces:
        ls = max(0.0, a - spec_start)
        le = max(0.0, b - spec_start)
        if le - ls > 0.05:
            locs.append((ls, le))
    if not locs:
        return [(0.0, dur)]
    tight = sum(le - ls for ls, le in locs)
    if dur - tight > max_remove + 0.08:
        return [(0.0, dur)]
    if len(locs) == 1:
        return [(locs[0][0], min(locs[0][1], dur))]
    return locs
