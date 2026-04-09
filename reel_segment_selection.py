#!/usr/bin/env python3
"""
Diverse segment selection for short-form reels: MMR over transcript/object text,
lexical boosts for humor / awe, and per-source caps to avoid one repetitive beat.

No extra ML deps — uses token overlap (Jaccard) + word/phrase hooks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


_WORD_RE = re.compile(r"[a-z0-9']+", re.I)

# Phrases/words suggesting humor (Instagram-style reaction, absurdity, surprise).
_HUMOR_SUBSTRINGS = (
    "haha",
    "ha ha",
    "lol",
    "funny",
    "laugh",
    "ridiculous",
    "kidding",
    "kidding me",
    "joke",
    "no way",
    "wait what",
    "what the",
    "can't believe",
    "cannot believe",
    "oh no",
    "oops",
    "yikes",
    "mess",
    "chaos",
    "wild",
    "insane",
    "crazy",
    "that's not",
    "that is not",
    "are you serious",
    "you serious",
)

# Awe / delight / beauty / milestone (reaction-friendly for Reels).
_AWE_SUBSTRINGS = (
    "wow",
    "whoa",
    "amazing",
    "beautiful",
    "incredible",
    "stunning",
    "gorgeous",
    "look at",
    "look at this",
    "first time",
    "never seen",
    "so cool",
    "so good",
    "so pretty",
    "breathtaking",
    "perfect",
    "delicious",
    "love it",
    "love this",
    "best thing",
    "oh my",
    "omg",
    "magical",
    "unreal",
    "spectacular",
)


def _normalize_text(s: str) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s)
    return t.lower().strip()


def social_hook_scores(text: str, duration_sec: float) -> Tuple[float, float, float]:
    """
    Returns (humor_0_1, awe_0_1, combined_boost) — combined_boost capped for blending.
    """
    t = _normalize_text(text)
    if not t:
        return 0.0, 0.0, 0.0
    h = 0.0
    for ph in _HUMOR_SUBSTRINGS:
        if ph in t:
            h += 1.0
    a = 0.0
    for ph in _AWE_SUBSTRINGS:
        if ph in t:
            a += 1.0
    # Diminishing returns
    h = min(1.0, h * 0.28)
    a = min(1.0, a * 0.28)
    # Slight preference for speech density (opinion beats)
    dens = 0.0
    if duration_sec > 0.2:
        wc = len(_WORD_RE.findall(t))
        dens = min(1.0, wc / max(2.0, duration_sec * 2.2))
    combined = min(0.28, 0.55 * max(h, a) + 0.12 * dens)
    return h, a, combined


def segment_plain_text(seg: Dict[str, Any]) -> str:
    parts: List[str] = []
    tr = seg.get("transcript") or {}
    if isinstance(tr, dict):
        parts.append(str(tr.get("full_text") or ""))
    parts.append(str(seg.get("summary") or ""))
    for o in seg.get("objects") or []:
        if isinstance(o, dict) and o.get("name"):
            parts.append(str(o["name"]))
    return " ".join(parts)


def token_set(text: str) -> Set[str]:
    return set(_WORD_RE.findall(_normalize_text(text)))


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _overlap_fraction(
    ranges: List[Tuple[float, float]], s: float, e: float, eps: float = 0.05
) -> bool:
    for a, b in ranges:
        if not (e <= a + eps or s >= b - eps):
            return True
    return False


@dataclass
class PickCandidate:
    fname: str
    seg: Dict[str, Any]
    start: float
    end: float
    raw_dur: float
    relevance: float
    humor: float
    awe: float
    tokens: Set[str] = field(default_factory=set)
    mid: float = 0.0

    def __post_init__(self) -> None:
        self.mid = (self.start + self.end) / 2.0


@dataclass
class ChosenSketch:
    fname: str
    start: float
    end: float
    tokens: Set[str]
    mid: float


def _similarity(a: PickCandidate | ChosenSketch, b: PickCandidate | ChosenSketch) -> float:
    t_sim = jaccard(a.tokens, b.tokens)
    same_file = 1.0 if a.fname == b.fname else 0.0
    if same_file < 0.5:
        return 0.55 * t_sim + 0.45 * same_file
    dt = abs(a.mid - b.mid)
    time_redundancy = 1.0 / (1.0 + dt / 6.0)
    return 0.45 * t_sim + 0.30 * same_file + 0.25 * time_redundancy


def _spec_from_candidate(
    c: PickCandidate,
    dur_use: float,
    reason: str,
    sid: str,
) -> Dict[str, Any]:
    e = c.start + dur_use
    return {
        "segment_id": sid,
        "video_file": c.fname,
        "time_range": {"start": c.start, "end": e},
        "keep_reason": reason,
    }


def build_pick_candidates(
    analyses: List[Dict[str, Any]],
    max_clip_seconds: float,
    min_clip_seconds: float,
) -> List[PickCandidate]:
    out: List[PickCandidate] = []
    for a in analyses:
        fname = a.get("file") or ""
        for seg in a.get("segments") or []:
            tr = seg.get("time_range") or {}
            s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
            raw_dur = max(0.0, e - s)
            if raw_dur < min_clip_seconds:
                continue
            text = segment_plain_text(seg)
            humor, awe, hook = social_hook_scores(text, raw_dur)
            editor = float(seg.get("editor_score", seg.get("quality_score", 0.5)))
            rel = editor * 0.78 + hook
            rel = min(1.0, max(0.0, rel))
            toks = token_set(text)
            out.append(
                PickCandidate(
                    fname=fname,
                    seg=seg,
                    start=s,
                    end=e,
                    raw_dur=raw_dur,
                    relevance=rel,
                    humor=humor,
                    awe=awe,
                    tokens=toks,
                )
            )
    out.sort(key=lambda x: -x.relevance)
    return out


def sketch_from_plan_spec(spec: Dict[str, Any], analyses: List[Dict[str, Any]]) -> Optional[ChosenSketch]:
    """Build similarity sketch from an existing editing-plan segment (e.g. Grok seed)."""
    vf = str(spec.get("video_file") or "")
    tr = spec.get("time_range") or {}
    s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
    if e <= s:
        return None
    text_parts: List[str] = []
    for a in analyses:
        if a.get("file") != vf:
            continue
        for seg in a.get("segments") or []:
            st = seg.get("time_range") or {}
            ss, se = float(st.get("start", 0)), float(st.get("end", 0))
            if ss <= s + 0.1 and se >= e - 0.1:
                text_parts.append(segment_plain_text(seg))
            elif not (se < s - 0.5 or ss > e + 0.5):
                text_parts.append(segment_plain_text(seg))
    if not text_parts:
        text_parts.append(vf)
    return ChosenSketch(
        fname=vf,
        start=s,
        end=e,
        tokens=token_set(" ".join(text_parts)),
        mid=(s + e) / 2.0,
    )


def mmr_pick_segments(
    analyses: List[Dict[str, Any]],
    body_budget: float,
    occupied: Dict[str, List[Tuple[float, float]]],
    file_used: Dict[str, float],
    used_so_far: float,
    max_clip_seconds: float,
    min_clip_seconds: float,
    chosen_sketches: List[ChosenSketch],
    *,
    id_start: int = 1,
    mmr_lambda: float = 0.74,
    max_file_fraction: float = 0.45,
) -> Tuple[List[Dict[str, Any]], List[str], float, Dict[str, List[Tuple[float, float]]], Dict[str, float]]:
    """
    Return new specs to append (not including seed), sequence ids, added duration,
    updated occupied, updated file_used.
    """
    cands = build_pick_candidates(analyses, max_clip_seconds, min_clip_seconds)
    selected: List[Dict[str, Any]] = []
    sequence: List[str] = []
    used = 0.0
    occ = {k: list(v) for k, v in occupied.items()}
    fu = dict(file_used)

    sketch_list = chosen_sketches
    max_per_file = max(8.0, max_file_fraction * body_budget)

    next_id = id_start
    idx = 0
    while used_so_far + used < body_budget - 0.25 and cands:
        best_i: Optional[int] = None
        best_score = -1e9
        for i, c in enumerate(cands):
            dur_cap = min(max_clip_seconds, c.raw_dur)
            if dur_cap < min_clip_seconds - 1e-6:
                continue
            rem = body_budget - used_so_far - used
            if rem < 0.25:
                break
            dur_use = min(dur_cap, rem)
            if dur_use < max(0.1, min_clip_seconds - 1e-6):
                continue
            if _overlap_fraction(occ.get(c.fname, []), c.start, c.start + dur_use):
                continue
            if fu.get(c.fname, 0.0) + dur_use > max_per_file + 0.05:
                continue

            if not sketch_list:
                mmr_s = c.relevance
            else:
                max_sim = max(_similarity(c, sk) for sk in sketch_list)
                mmr_s = mmr_lambda * c.relevance - (1.0 - mmr_lambda) * max_sim
            if mmr_s > best_score:
                best_score = mmr_s
                best_i = i

        if best_i is None:
            # Relax file cap slightly — still avoid overlap
            relaxed = max_per_file + body_budget * 0.12
            for i, c in enumerate(cands):
                dur_cap = min(max_clip_seconds, c.raw_dur)
                rem = body_budget - used_so_far - used
                dur_use = min(dur_cap, rem)
                if dur_use < max(0.1, min_clip_seconds - 1e-6):
                    continue
                if _overlap_fraction(occ.get(c.fname, []), c.start, c.start + dur_use):
                    continue
                if fu.get(c.fname, 0.0) + dur_use > relaxed:
                    continue
                if not sketch_list:
                    mmr_s = c.relevance
                else:
                    max_sim = max(_similarity(c, sk) for sk in sketch_list)
                    mmr_s = mmr_lambda * c.relevance - (1.0 - mmr_lambda) * max_sim
                if mmr_s > best_score:
                    best_score = mmr_s
                    best_i = i
            if best_i is None:
                break

        c = cands.pop(best_i)
        rem = body_budget - used_so_far - used
        dur_cap = min(max_clip_seconds, c.raw_dur)
        dur_use = min(dur_cap, rem)
        e_use = c.start + dur_use
        sid = f"mmr_{next_id:03d}"
        next_id += 1
        hook_note = ""
        if c.humor > 0.15 or c.awe > 0.15:
            hook_note = f" hooks humor={c.humor:.2f}/awe={c.awe:.2f}"
        reason = f"MMR reel rel={c.relevance:.2f}{hook_note}"
        spec = _spec_from_candidate(c, dur_use, reason, sid)
        selected.append(spec)
        sequence.append(sid)
        occ.setdefault(c.fname, []).append((c.start, e_use))
        fu[c.fname] = fu.get(c.fname, 0.0) + dur_use
        used += dur_use
        sketch_list.append(
            ChosenSketch(
                fname=c.fname,
                start=c.start,
                end=e_use,
                tokens=c.tokens,
                mid=(c.start + e_use) / 2.0,
            )
        )

        idx += 1
        if idx > 200:
            break

    return selected, sequence, used, occ, fu


def timeline_fill_diverse(
    analyses: List[Dict[str, Any]],
    body_budget: float,
    occupied: Dict[str, List[Tuple[float, float]]],
    file_used: Dict[str, float],
    used_so_far: float,
    max_clip_seconds: float,
    max_file_fraction: float = 0.48,
) -> Tuple[List[Dict[str, Any]], List[str], float, Dict[str, List[Tuple[float, float]]], Dict[str, float]]:
    """Gap-fill like the old timeline pass but skips files already over cap when possible."""

    def merge_intervals(ranges: List[Tuple[float, float]], eps: float = 0.05) -> List[Tuple[float, float]]:
        if not ranges:
            return []
        sr = sorted(ranges, key=lambda x: x[0])
        out: List[Tuple[float, float]] = [(sr[0][0], sr[0][1])]
        for s, e in sr[1:]:
            ps, pe = out[-1]
            if s <= pe + eps:
                out[-1] = (ps, max(pe, e))
            else:
                out.append((s, e))
        return out

    def vid_avg(a: Dict[str, Any]) -> float:
        segs = a.get("segments") or []
        if not segs:
            return 0.28
        acc = sum(float(s.get("editor_score", s.get("quality_score", 0.35))) for s in segs)
        return max(0.2, acc / len(segs))

    selected: List[Dict[str, Any]] = []
    sequence: List[str] = []
    used = 0.0
    occ = {k: list(v) for k, v in occupied.items()}
    fu = dict(file_used)
    max_per_file = max(10.0, max_file_fraction * body_budget)

    if used_so_far + used >= body_budget - 0.25:
        return selected, sequence, used, occ, fu

    for a in analyses:
        if used_so_far + used >= body_budget - 0.25:
            break
        fname = a.get("file") or ""
        meta = a.get("metadata") or {}
        total = float(meta.get("duration", 0) or 0)
        if total <= 0:
            continue
        gap_score = vid_avg(a) * 0.52
        merged = merge_intervals(occ.get(fname, []))
        cursor = 0.0
        for bs, be in merged:
            while cursor < bs - 0.05 and used_so_far + used < body_budget - 0.25:
                chunk_end = min(bs, cursor + max_clip_seconds)
                d = chunk_end - cursor
                if d >= 1.0:
                    if fu.get(fname, 0.0) + d > max_per_file + 0.2:
                        cursor = chunk_end
                        continue
                    sid = f"fill_{len(sequence)+1:03d}"
                    selected.append(
                        {
                            "segment_id": sid,
                            "video_file": fname,
                            "time_range": {"start": cursor, "end": chunk_end},
                            "keep_reason": f"timeline fill score={gap_score:.2f}",
                        }
                    )
                    sequence.append(sid)
                    occ.setdefault(fname, []).append((cursor, chunk_end))
                    fu[fname] = fu.get(fname, 0.0) + d
                    used += d
                    cursor = chunk_end
                else:
                    cursor = bs
            cursor = max(cursor, be)
        while cursor < total - 0.05 and used_so_far + used < body_budget - 0.25:
            chunk_end = min(total, cursor + max_clip_seconds)
            d = chunk_end - cursor
            if d >= 1.0:
                if fu.get(fname, 0.0) + d > max_per_file + 0.2:
                    cursor = chunk_end
                    continue
                sid = f"fill_{len(sequence)+1:03d}"
                selected.append(
                    {
                        "segment_id": sid,
                        "video_file": fname,
                        "time_range": {"start": cursor, "end": chunk_end},
                        "keep_reason": f"timeline fill score={gap_score:.2f}",
                    }
                )
                sequence.append(sid)
                occ.setdefault(fname, []).append((cursor, chunk_end))
                fu[fname] = fu.get(fname, 0.0) + d
                used += d
                cursor = chunk_end
            else:
                break

    return selected, sequence, used, occ, fu
