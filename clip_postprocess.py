#!/usr/bin/env python3
"""
Post-process editing plans: file creation order, chronological timeline,
speech-friendly tail padding, hard duration ceiling (target * factor).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_FILLER = frozenset(
    {
        "um",
        "uh",
        "uhh",
        "ah",
        "ahh",
        "erm",
        "er",
        "like",
        "hmm",
        "hm",
        "mm",
        "mhm",
        "umm",
        "uhm",
    }
)
_WORD_CLEAN = re.compile(r"[^a-z0-9']+", re.I)


def file_creation_timestamp(path: Path) -> float:
    """Prefer birth time (macOS); fall back to mtime."""
    try:
        s = path.stat()
        bt = getattr(s, "st_birthtime", None)
        if bt is not None and bt > 0:
            return float(bt)
    except OSError:
        pass
    return float(path.stat().st_mtime)


def sort_paths_by_creation_time(paths: List[Path]) -> List[Path]:
    return sorted(paths, key=file_creation_timestamp)


def reorder_plan_chronologically(plan: Dict[str, Any], path_by_file: Dict[str, str]) -> None:
    """Sort sequence by file creation time, then in-file start time. Mutates plan."""
    ep = plan.get("editing_plan") or {}
    segs = ep.get("selected_segments") or []
    order = list(ep.get("sequence") or [])
    by_id = {s.get("segment_id"): s for s in segs}
    specs: List[Dict[str, Any]] = []
    for sid in order:
        sp = by_id.get(sid)
        if sp:
            specs.append(sp)

    def sort_key(sp: Dict[str, Any]) -> Tuple[float, float, float]:
        vf = str(sp.get("video_file") or "")
        p = Path(path_by_file.get(vf) or "")
        tr = sp.get("time_range") or {}
        s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
        return (file_creation_timestamp(p) if p.is_file() else 0.0, s, e)

    specs.sort(key=sort_key)
    ep["sequence"] = [str(s.get("segment_id")) for s in specs if s.get("segment_id")]


def _norm_tok(s: str) -> str:
    return _WORD_CLEAN.sub("", (s or "").lower()).strip()


def _words_overlapping_range(
    analysis: Dict[str, Any], start: float, end: float, pad: float = 0.5
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lo, hi = start - pad, end + pad
    for seg in analysis.get("segments") or []:
        tr = seg.get("time_range") or {}
        ss, se = float(tr.get("start", 0)), float(tr.get("end", 0))
        if se < lo or ss > hi:
            continue
        tw = (seg.get("transcript") or {}).get("words") or []
        for w in tw:
            ws, we = float(w.get("start", 0)), float(w.get("end", 0))
            if we < lo or ws > hi:
                continue
            out.append(w)
    out.sort(key=lambda x: float(x.get("end", 0)))
    return out


def _last_meaningful_word_end(words: List[Dict[str, Any]], before: float) -> Optional[float]:
    cand = [w for w in words if float(w.get("end", 0)) <= before + 0.03]
    if not cand:
        return None
    for w in reversed(cand):
        tok = _norm_tok(str(w.get("word", "")))
        if not tok or tok in _FILLER:
            continue
        return float(w.get("end", 0))
    return float(cand[-1].get("end", 0))


def speech_tail_padded_end(
    analysis: Dict[str, Any],
    start: float,
    end: float,
    file_duration: float,
    *,
    tail_lo: float = 0.5,
    tail_hi: float = 1.0,
    max_silence_after_speech: float = 0.52,
) -> float:
    """Extend segment end slightly so speech can land; avoid long dead air after fillers."""
    if file_duration <= 0:
        return end
    words = _words_overlapping_range(analysis, start, end)
    target = min(file_duration, end + (tail_lo + tail_hi) / 2.0)
    lm = _last_meaningful_word_end(words, end)
    if lm is None:
        return min(file_duration, max(end + tail_lo * 0.85, min(end + tail_hi, target)))

    if target - lm > max_silence_after_speech:
        target = lm + max_silence_after_speech
    target = max(target, min(end + tail_lo, file_duration))
    target = min(target, end + tail_hi, file_duration)
    if target < end + 0.28:
        target = min(file_duration, end + tail_lo)
    return float(target)


def apply_tail_padding_to_plan(
    plan: Dict[str, Any],
    analyses_by_file: Dict[str, Dict[str, Any]],
    path_by_file: Dict[str, str],
    *,
    tail_lo: float = 0.5,
    tail_hi: float = 1.0,
) -> None:
    """Mutate each selected_segment time_range end in sequence order."""
    ep = plan.get("editing_plan") or {}
    by_id = {s.get("segment_id"): s for s in ep.get("selected_segments") or []}
    for sid in ep.get("sequence") or []:
        spec = by_id.get(sid)
        if not spec:
            continue
        vf = str(spec.get("video_file") or "")
        an = analyses_by_file.get(vf) or {}
        meta = an.get("metadata") or {}
        fd = float(meta.get("duration", 0) or 0)
        tr = spec.get("time_range") or {}
        s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
        if fd <= 0:
            continue
        ne = speech_tail_padded_end(an, s, e, fd, tail_lo=tail_lo, tail_hi=tail_hi)
        ne = max(ne, s + 0.12)
        spec["time_range"] = {"start": s, "end": round(ne, 3)}


def trim_plan_to_duration_ceiling(plan: Dict[str, Any], ceiling_sec: float, min_clip: float = 0.32) -> None:
    """If total body > ceiling, shave time from the end of clips (last first). Mutates plan."""
    ep = plan.get("editing_plan") or {}
    order = list(ep.get("sequence") or [])
    by_id = {s.get("segment_id"): s for s in ep.get("selected_segments") or []}

    def body() -> float:
        t = 0.0
        for sid in order:
            sp = by_id.get(sid)
            if not sp:
                continue
            tr = sp.get("time_range") or {}
            t += max(0.0, float(tr.get("end", 0)) - float(tr.get("start", 0)))
        return t

    excess = body() - ceiling_sec
    if excess <= 0.02:
        return

    for sid in reversed(order):
        if excess <= 0.02:
            break
        sp = by_id.get(sid)
        if not sp:
            continue
        tr = sp.get("time_range") or {}
        s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
        dur = e - s
        room = dur - min_clip
        if room <= 0:
            continue
        shave = min(excess, room)
        e -= shave
        excess -= shave
        sp["time_range"] = {"start": s, "end": round(e, 3)}
