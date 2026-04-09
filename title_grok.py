#!/usr/bin/env python3
"""Grok-generated two-line on-screen hooks from full multi-clip transcripts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Tight cap for large drawtext on 1080px-wide vertical frame (see build_short_from_folder).
OVERLAY_LINE_MAX_CHARS = 20

_SYSTEM = f"""You write ultra-short on-screen hooks for Instagram Reels / YouTube Shorts (9:16).
Output ONLY valid JSON, no markdown, no extra keys:
{{"line1":"<string>","line2":"<string>","angle":"funny"|"curiosity"}}

Rules:
- line1 and line2: each MUST be at most {OVERLAY_LINE_MAX_CHARS} characters (count spaces). Billboard copy only.
- The hook must be grounded in the transcript: do not invent events or people not supported by what was said.
- Pick ONE dominant vibe: either FUNNY (playful, wry, absurd-but-true) OR CURIOSITY (mystery, contrarian, "wait what", bold claim) — set "angle" accordingly.
- No hashtags, no emojis, no quotes inside lines.
- Prefer concrete food/process words when they fit (cacao, roast, chocolate, cup) if transcript supports it.
"""


def _clip_middle(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    head = int(max_len * 0.62)
    tail = max_len - head - 25
    if tail < 80:
        tail = 80
    return s[:head] + "\n...[truncated]...\n" + s[-tail:]


def build_full_transcript_context(analyses: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """Chronological-ish dump of all clip transcripts for Grok (labeled by file)."""
    parts: List[str] = []
    for a in analyses:
        fn = str(a.get("file") or "").strip() or "clip"
        lines: List[str] = []
        for seg in a.get("segments") or []:
            tr = (seg.get("transcript") or {}).get("full_text") or ""
            tr = str(tr).strip()
            if not tr:
                continue
            tr_rng = seg.get("time_range") or {}
            t0 = float(tr_rng.get("start", 0))
            t1 = float(tr_rng.get("end", 0))
            lines.append(f"  [{t0:.1f}–{t1:.1f}s] {tr}")
        if lines:
            parts.append(f"=== {fn} ===\n" + "\n".join(lines))
    blob = "\n\n".join(parts).strip()
    if not blob:
        return ""
    return _clip_middle(blob, max_chars)


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    s = raw.strip()
    if "```json" in s:
        a = s.find("```json") + 7
        b = s.find("```", a)
        if b > a:
            s = s[a:b].strip()
    elif "```" in s:
        a = s.find("```") + 3
        b = s.find("```", a)
        if b > a:
            s = s[a:b].strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\"line1\"[^{}]*\}", s, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def _clamp_line(s: str, max_c: int) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip())
    if len(t) <= max_c:
        return t
    t = t[: max_c - 1].rsplit(" ", 1)[0].strip()
    if len(t) > max_c - 1:
        t = t[: max_c - 1].rstrip()
    return (t + "…")[:max_c]


def grok_overlay_title_lines(
    full_transcript_blob: str,
    opening_snippet: str,
    *,
    template_hint: str = "",
) -> Optional[Tuple[str, str, str]]:
    """
    Returns (line1, line2, angle) or None on failure.

    Calls Grok; requires GROK_API_KEY.
    """
    from grok_client import grok_chat_completion

    if not full_transcript_blob.strip():
        return None

    hint = (template_hint or "").strip()
    open_h = (opening_snippet or "").strip()[:800]
    user = (
        "FULL TRANSCRIPT (all clips, may be truncated):\n"
        f"{full_transcript_blob}\n\n"
        "FIRST-CLIP SPOKEN CONTEXT (optional tie-in; hook may reference broader arc):\n"
        f"{open_h or '(none)'}\n\n"
    )
    if hint:
        user += f"EDITOR TEMPLATE / INTENT:\n{hint}\n\n"
    user += (
        f"Return JSON only. line1 and line2 each ≤{OVERLAY_LINE_MAX_CHARS} characters. "
        'angle is "funny" or "curiosity".'
    )

    content = grok_chat_completion(_SYSTEM, user, temperature=0.82, timeout=50)
    obj = _parse_json_object(content)
    if not obj:
        return None
    l1 = _clamp_line(str(obj.get("line1") or ""), OVERLAY_LINE_MAX_CHARS)
    l2 = _clamp_line(str(obj.get("line2") or ""), OVERLAY_LINE_MAX_CHARS)
    ang = str(obj.get("angle") or "").lower()
    if ang not in ("funny", "curiosity"):
        ang = "curiosity"
    if len(l1) < 2:
        return None
    return l1, l2, ang
