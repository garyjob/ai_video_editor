#!/usr/bin/env python3
"""Wrap on-screen title lines to a max pixel width (e.g. 50% of 1080)."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

try:
    from PIL import ImageFont
except ImportError:
    ImageFont = None  # type: ignore


def _text_width_px(text: str, font_path: Optional[str], fontsize: int) -> float:
    if not text:
        return 0.0
    if font_path and ImageFont is not None:
        try:
            f = ImageFont.truetype(font_path, fontsize)
            bbox = f.getbbox(text)
            return float(bbox[2] - bbox[0])
        except OSError:
            pass
    return float(len(text)) * fontsize * 0.58


def wrap_to_max_width(
    text: str,
    *,
    font_path: Optional[str],
    fontsize: int,
    max_width_px: float,
    max_lines: int,
) -> List[str]:
    """Word-wrap to <= max_width_px; cap at max_lines (last line ellipsized if needed)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    words = t.split()
    lines: List[str] = []
    cur: List[str] = []
    for w in words:
        trial = " ".join(cur + [w]) if cur else w
        if _text_width_px(trial, font_path, fontsize) <= max_width_px or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if not lines:
        return []
    consumed = sum(len(line.split()) for line in lines)
    if consumed < len(words) and lines:
        last = lines[-1]
        trial = last + "…"
        if _text_width_px(trial, font_path, fontsize) <= max_width_px:
            lines[-1] = trial
        else:
            while " " in last and _text_width_px(last + "…", font_path, fontsize) > max_width_px:
                last = last.rsplit(" ", 1)[0].strip()
            lines[-1] = (last + "…") if last else "…"
    return lines


def layout_hook_and_brand(
    line1: str,
    line2: str,
    brand: str,
    *,
    font_path: Optional[str],
    frame_width: int = 1080,
    max_width_fraction: float = 0.5,
    fs_main: int = 96,
    fs_brand: int = 46,
    max_hook_lines: int = 5,
    max_brand_lines: int = 2,
) -> Tuple[List[str], List[str]]:
    """Return (hook_lines, brand_lines) for stacked drawtext; center-aligned block."""
    margin = 24.0
    max_px = float(frame_width) * float(max_width_fraction) - margin
    hook_blob = f"{(line1 or '').strip()} {(line2 or '').strip()}".strip()
    hook_lines = wrap_to_max_width(
        hook_blob,
        font_path=font_path,
        fontsize=fs_main,
        max_width_px=max_px,
        max_lines=max_hook_lines,
    )
    if not hook_lines:
        hook_lines = [(line1 or "").strip() or "…"]
    brand_lines = wrap_to_max_width(
        (brand or "").strip(),
        font_path=font_path,
        fontsize=fs_brand,
        max_width_px=max_px,
        max_lines=max_brand_lines,
    )
    if not brand_lines and (brand or "").strip():
        brand_lines = [(brand or "").strip()[:40]]
    return hook_lines, brand_lines
