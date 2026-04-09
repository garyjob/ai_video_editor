#!/usr/bin/env python3
"""Build 2-line opening overlay copy from Whisper transcript (first clip window)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Fallback when there is no usable speech in the opening clip.
DEFAULT_OVERLAY_LINE1 = "Roasting chocolate"
DEFAULT_OVERLAY_LINE2 = "with Mulan"
DEFAULT_BRAND_LINE = "Agroverse"


def _norm(s: str) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _overlap_seconds(
    seg_start: float, seg_end: float, win_start: float, win_end: float
) -> float:
    return max(0.0, min(seg_end, win_end) - max(seg_start, win_start))


def collect_transcript_in_window(
    analysis: Dict[str, Any], win_start: float, win_end: float
) -> str:
    """Concatenate transcript snippets from segments that meaningfully overlap the clip window."""
    if win_end <= win_start:
        return ""
    pieces: List[str] = []
    seen: set[str] = set()
    for seg in analysis.get("segments") or []:
        tr = seg.get("time_range") or {}
        s = float(tr.get("start", 0))
        e = float(tr.get("end", 0))
        if e <= s:
            continue
        ov = _overlap_seconds(s, e, win_start, win_end)
        dur = e - s
        if ov < 0.35 and ov < 0.2 * dur:
            continue
        text = _norm((seg.get("transcript") or {}).get("full_text") or "")
        if len(text) < 2:
            continue
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        pieces.append(text)
    return _norm(" ".join(pieces))


def _split_at_boundary(text: str, max_first: int, max_second: int) -> Tuple[str, str]:
    """Prefer splitting on punctuation / conjunction; else split on word near midpoint."""
    t = _norm(text)
    if not t:
        return "", ""
    if len(t) <= max_first:
        return t, ""
    # Try boundaries in first chunk
    chunk = t[: max_first + 12]
    for sep in (", ", " — ", " - ", "; ", ". ", " and ", " but "):
        idx = chunk.rfind(sep)
        if idx >= 8:
            a, b = t[: idx + len(sep)].strip().rstrip(",").strip(), t[idx + len(sep) :].strip()
            if len(a) <= max_first + 6 and len(b) <= max_second + 10:
                return a, b
    # Mid-word split
    words = t.split()
    if not words:
        return t[:max_first], t[max_first:]
    acc: List[str] = []
    rest_start = 0
    for i, w in enumerate(words):
        trial = " ".join(acc + [w]) if acc else w
        if len(trial) <= max_first:
            acc.append(w)
            rest_start = i + 1
        else:
            break
    if not acc:
        acc = [words[0]]
        rest_start = 1
    line1 = " ".join(acc)
    line2 = " ".join(words[rest_start:]).strip()
    if len(line1) > max_first + 8:
        line1 = line1[: max_first + 5].rstrip() + "…"
    if len(line2) > max_second + 8:
        line2 = line2[: max_second + 5].rstrip() + "…"
    return line1, line2


def transcript_to_two_lines(text: str) -> Tuple[str, str]:
    """Fit transcribed hook to two readable overlay lines (9:16)."""
    t = _norm(text)
    if len(t) < 3:
        return "", ""
    # Tuned for ~96px drawtext on 1080-wide vertical (keep lines short; avoids side clip).
    max_first, max_second = 18, 20
    return _split_at_boundary(t, max_first, max_second)


def overlay_lines_from_first_clip(
    spec: Dict[str, Any],
    analyses_by_file: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Return (line1, line2) for the opening hook from speech in the first clip's time_range.
    Falls back to DEFAULT_OVERLAY_LINE1/2 if there is no usable transcript.
    """
    vf = str(spec.get("video_file") or "")
    analysis = analyses_by_file.get(vf)
    if not analysis:
        return DEFAULT_OVERLAY_LINE1, DEFAULT_OVERLAY_LINE2
    tr = spec.get("time_range") or {}
    start = float(tr.get("start", 0))
    end = float(tr.get("end", start + 1))
    blob = collect_transcript_in_window(analysis, start, end)
    line1, line2 = transcript_to_two_lines(blob)
    if len(line1) < 2:
        return DEFAULT_OVERLAY_LINE1, DEFAULT_OVERLAY_LINE2
    return line1, line2
