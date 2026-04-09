#!/usr/bin/env python3
"""
Analyze clips in a folder (Whisper + YOLO + scene + motion), rank via Grok or
local MMR selection (diverse + humor/awe hooks), render ~30s 9:16 letterboxed short.

Keeps source audio (AAC in output). Title is overlaid on the first clip
(yellow / outline / purple shadow, Arial Rounded on macOS), not a separate
solid-color card; the hook is drawn on a transparent layer, tilted slightly
(~6°) for a more social / energetic read. Opening hook: Grok writes 2 ultra-short lines from the **full** multi-clip
transcript (funny or curiosity), capped for large type; fallback is first-clip
Whisper. Manual: --title-line1/--title-line2. Brand: --brand-line (default Agroverse).

Usage:
  ./venv/bin/python build_short_from_folder.py /path/to/folder [--limit 4] [--target 30]
  ./venv/bin/python build_short_from_folder.py /path/to/folder --target 60 --out-suffix 60s
  ./venv/bin/python build_short_from_folder.py /path/to/folder --flexible-duration --max-total-sec 120

Requires: ffmpeg, venv deps (whisper, ultralytics, opencv optional).
Grok optional: GROK_API_KEY in .env

Re-analyze only when a clip changes (size/mtime) or EXTRACTION_PIPELINE_VERSION
in analysis_cache.py is bumped.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analysis_cache import (
    load_cached_analysis,
    save_cached_analysis,
    cache_json_path,
)
from clip_postprocess import (
    apply_tail_padding_to_plan,
    reorder_plan_chronologically,
    sort_paths_by_creation_time,
    trim_plan_to_duration_ceiling,
)
from grok_client import get_grok_api_key
from title_from_transcript import (
    DEFAULT_BRAND_LINE,
    DEFAULT_OVERLAY_LINE1,
    DEFAULT_OVERLAY_LINE2,
    collect_transcript_in_window,
    overlay_lines_from_first_clip,
)
from title_grok import build_full_transcript_context, grok_overlay_title_lines
from title_layout import layout_hook_and_brand
from speech_tighten import local_keep_intervals_simple
from reel_segment_selection import (
    mmr_pick_segments,
    sketch_from_plan_spec,
    timeline_fill_diverse,
)


def _intervals_overlap(s1: float, e1: float, s2: float, e2: float, eps: float = 0.05) -> bool:
    return not (e1 <= s2 + eps or s1 >= e2 - eps)


def _overlaps_any(ranges: List[Tuple[float, float]], s: float, e: float) -> bool:
    for a, b in ranges:
        if _intervals_overlap(s, e, a, b):
            return True
    return False


def _merge_intervals(ranges: List[Tuple[float, float]], eps: float = 0.05) -> List[Tuple[float, float]]:
    if not ranges:
        return []
    sorted_r = sorted(ranges, key=lambda x: x[0])
    out: List[Tuple[float, float]] = [(sorted_r[0][0], sorted_r[0][1])]
    for s, e in sorted_r[1:]:
        ps, pe = out[-1]
        if s <= pe + eps:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def _ffprobe_has_audio(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe") or "/usr/local/bin/ffprobe"
    r = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return "audio" in r.stdout.lower()


def _default_rounded_title_font() -> Optional[str]:
    for p in (
        Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"),
        Path("/Library/Fonts/Arial Rounded Bold.ttf"),
    ):
        if p.is_file():
            return str(p)
    return None


def _escape_drawtext_fontfile(path: str) -> str:
    """Escape a filesystem path for use in drawtext fontfile= inside -vf."""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _escape_filter_path(p: str) -> str:
    """Escape a path for use in drawtext fontfile=/ textfile= inside -vf."""
    return (
        p.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(" ", "\\ ")
    )


# Title block lean (~10° CCW feels energetic; drawn on rgba then rotated — see ffmpeg_extract_letterbox).
_TITLE_TILT_RAD = -0.11
_TITLE_ROT_W = 2480
_TITLE_ROT_H = 2850


_TITLE_FS_MAIN = 96
_TITLE_FS_SUB = 46


def _title_overlay_drawtext_chain(
    overlay_sec: float,
    hook_paths: List[Path],
    brand_paths: List[Path],
) -> str:
    """Stacked drawtext: UTF-8 textfiles, centered (max width enforced in layout)."""

    en = f"between(t\\,0\\,{overlay_sec:.3f})"
    font = _default_rounded_title_font()
    font_opt = ""
    if font:
        font_opt = f":fontfile={_escape_drawtext_fontfile(font)}"
    fs_main = _TITLE_FS_MAIN
    fs_sub = _TITLE_FS_SUB
    shadow = ":shadowx=7:shadowy=11:shadowcolor=0x5E35B1"
    outline = ":borderw=5:bordercolor=black"
    parts: List[str] = []
    y0 = 0.36
    lh_main = 108
    gap_before_brand = 36
    yi = y0
    for p in hook_paths:
        pp = _escape_filter_path(str(p.resolve()))
        parts.append(
            f"drawtext=textfile='{pp}'{font_opt}:reload=0:fontsize={fs_main}:fontcolor=#FFDD00"
            f"{outline}{shadow}:fix_bounds=1"
            f":x=(w-text_w)/2:y=h*{yi:.4f}:enable='{en}'"
        )
        yi += lh_main / 1920.0
    if brand_paths:
        yi += gap_before_brand / 1920.0
    for p in brand_paths:
        pp = _escape_filter_path(str(p.resolve()))
        parts.append(
            f"drawtext=textfile='{pp}'{font_opt}:reload=0:fontsize={fs_sub}:fontcolor=#FFFFFF:borderw=3"
            f":bordercolor=black:shadowx=4:shadowy=5:shadowcolor=0x333333:fix_bounds=1"
            f":x=(w-text_w)/2:y=h*{yi:.4f}:enable='{en}'"
        )
        yi += 52 / 1920.0
    return ",".join(parts)


def _editing_plan_body_seconds(editing_plan: Dict[str, Any]) -> float:
    segs = editing_plan.get("selected_segments") or []
    t = 0.0
    for s in segs:
        tr = s.get("time_range") or {}
        t += max(0.0, float(tr.get("end", 0)) - float(tr.get("start", 0)))
    return t


def local_editing_plan(
    analyses: List[Dict[str, Any]],
    target_seconds: float,
    title_seconds: float = 0.0,
    max_clip_seconds: float = 7.0,
    min_clip_seconds: float = 2.5,
    seed_from_editing_plan: Optional[Dict[str, Any]] = None,
    metadata_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fill body budget with diverse, Reel-friendly picks (minus title_seconds if any).

    After optional Grok seed order, uses MMR over transcript/object text (humor/awe
    hooks, editor_score), per-file caps, then capped timeline gap fill.

    If ``seed_from_editing_plan`` is set (e.g. a Grok plan), those segments are
    kept first in order; remaining body time is filled with MMR + timeline fill
    (diverse picks, humor/awe hooks, per-file caps).
    """
    body_budget = max(5.0, target_seconds - title_seconds)
    occupied: Dict[str, List[Tuple[float, float]]] = {}

    selected: List[Dict[str, Any]] = []
    sequence: List[str] = []
    used = 0.0

    if seed_from_editing_plan:
        segs = list(seed_from_editing_plan.get("selected_segments") or [])
        order = list(seed_from_editing_plan.get("sequence") or [])
        by_id = {s.get("segment_id"): s for s in segs}
        for sid in order:
            spec = by_id.get(sid)
            if not spec:
                continue
            vf = str(spec.get("video_file") or "")
            tr = spec.get("time_range") or {}
            s, e = float(tr.get("start", 0)), float(tr.get("end", 0))
            dur = max(0.0, e - s)
            if dur < 0.05:
                continue
            selected.append(dict(spec))
            sequence.append(str(sid))
            occupied.setdefault(vf, []).append((s, e))
            used += dur

    chosen_sketches = []
    for spec in selected:
        sk = sketch_from_plan_spec(spec, analyses)
        if sk:
            chosen_sketches.append(sk)

    file_used: Dict[str, float] = {}
    for spec in selected:
        vf = str(spec.get("video_file") or "")
        tr = spec.get("time_range") or {}
        file_used[vf] = file_used.get(vf, 0.0) + max(
            0.0, float(tr.get("end", 0)) - float(tr.get("start", 0))
        )

    mmr_next = 1
    if used < body_budget - 0.25:
        specs_m, seq_m, du_m, occupied, file_used = mmr_pick_segments(
            analyses,
            body_budget,
            occupied,
            file_used,
            used,
            max_clip_seconds,
            min_clip_seconds,
            chosen_sketches,
            id_start=mmr_next,
        )
        mmr_next += len(specs_m)
        selected.extend(specs_m)
        sequence.extend(seq_m)
        used += du_m

    if used < body_budget - 1.0:
        specs_m2, seq_m2, du_m2, occupied, file_used = mmr_pick_segments(
            analyses,
            body_budget,
            occupied,
            file_used,
            used,
            max_clip_seconds,
            1.0,
            chosen_sketches,
            id_start=mmr_next,
        )
        mmr_next += len(specs_m2)
        selected.extend(specs_m2)
        sequence.extend(seq_m2)
        used += du_m2

    if used < body_budget - 0.5:
        specs_t, seq_t, du_t, occupied, file_used = timeline_fill_diverse(
            analyses,
            body_budget,
            occupied,
            file_used,
            used,
            max_clip_seconds,
        )
        selected.extend(specs_t)
        sequence.extend(seq_t)
        used += du_t

    meta = metadata_override if metadata_override is not None else {
        "title": "Short (local rank)",
        "description": "",
        "tags": [],
        "category": "Howto",
    }
    return {
        "editing_plan": {
            "target_duration_seconds": target_seconds,
            "selected_segments": selected,
            "sequence": sequence,
            "trim_suggestions": [],
            "total_duration": used + title_seconds,
            "final_duration": used + title_seconds,
            "transitions": [],
        },
        "metadata": dict(meta),
    }


def ffmpeg_title(out: Path, seconds: float = 2.0) -> None:
    """Solid-color title card (legacy). Prefer title overlay on first clip instead."""
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    vf = (
        "format=yuv420p,"
        "drawtext=text='Roasting chocolate with Mulan':fontcolor=#f5e6d3:fontsize=44:x=(w-text_w)/2:y=(h-text_h)/2-40,"
        "drawtext=text='Ranked clip picks | Agroverse':fontcolor=#c4b5a0:fontsize=26:x=(w-text_w)/2:y=(h-text_h)/2+50"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x2a1810:s=1080x1920:d={seconds}:r=30000/1001",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def ffmpeg_extract_letterbox(
    src: Path,
    start: float,
    duration: float,
    out: Path,
    title_overlay_sec: Optional[float] = None,
    title_lines: Optional[Tuple[str, str, str]] = None,
    local_intervals: Optional[List[Tuple[float, float]]] = None,
    title_max_width_frac: float = 0.5,
) -> None:
    """Extract segment, letterbox to 1080x1920, keep audio as AAC when present.

    If ``local_intervals`` has multiple disjoint ranges (seconds relative to ``start``),
    trims and concatenates before letterbox. Single interval ``(0, duration)`` uses
    one pass.
    """
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    rate = "30000/1001"
    vf_scale_pad = (
        "scale=1080:-2:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x1a1512,format=yuv420p"
    )

    intr = local_intervals or [(0.0, float(duration))]
    intr = [(max(0.0, a), min(float(duration), b)) for a, b in intr if b - a > 0.04]
    if not intr:
        intr = [(0.0, float(duration))]
    use_multi = len(intr) > 1 or (
        len(intr) == 1
        and (intr[0][0] > 0.06 or intr[0][1] < float(duration) - 0.08)
    )

    use_tilt_title = bool(title_overlay_sec and title_overlay_sec > 0)
    title_chain = ""
    out_tight = sum(b - a for a, b in intr)
    d_color = f"{max(0.01, float(out_tight)):.6f}".rstrip("0").rstrip(".") or "0.01"

    if use_tilt_title:
        l1, l2, sub = title_lines or (
            DEFAULT_OVERLAY_LINE1,
            DEFAULT_OVERLAY_LINE2,
            DEFAULT_BRAND_LINE,
        )
        fp = _default_rounded_title_font()
        hook_lines, brand_lines = layout_hook_and_brand(
            l1 or "",
            l2 or "",
            sub or "",
            font_path=fp,
            frame_width=1080,
            max_width_fraction=title_max_width_frac,
            fs_main=_TITLE_FS_MAIN,
            fs_brand=_TITLE_FS_SUB,
        )
        if not brand_lines and (sub or "").strip():
            brand_lines = [(sub or "").strip()]
        hook_paths: List[Path] = []
        for i, h in enumerate(hook_lines):
            p = out.parent / f"{out.stem}_hook_{i}.txt"
            p.write_text(h.strip() + "\n", encoding="utf-8")
            hook_paths.append(p)
        brand_paths: List[Path] = []
        for i, b in enumerate(brand_lines):
            p = out.parent / f"{out.stem}_brand_{i}.txt"
            p.write_text(b.strip() + "\n", encoding="utf-8")
            brand_paths.append(p)
        title_chain = _title_overlay_drawtext_chain(
            float(title_overlay_sec), hook_paths, brand_paths
        )

    has_audio = _ffprobe_has_audio(src)
    cmd: List[str] = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(src),
    ]
    if not has_audio:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]

    if use_multi and not use_tilt_title:
        v_parts: List[str] = []
        a_parts: List[str] = []
        for i, (ls, le) in enumerate(intr):
            v_parts.append(
                f"[0:v]trim=start={ls:.3f}:end={le:.3f},setpts=PTS-STARTPTS[v{i}];"
            )
        nv = len(intr)
        vconcat = "".join(f"[v{i}]" for i in range(nv)) + f"concat=n={nv}:v=1:a=0[vc];"
        vchain = "".join(v_parts) + vconcat + f"[vc]{vf_scale_pad}[outv]"
        if has_audio:
            for i, (ls, le) in enumerate(intr):
                a_parts.append(
                    f"[0:a]atrim=start={ls:.3f}:end={le:.3f},asetpts=PTS-STARTPTS[a{i}];"
                )
            achain = "".join(a_parts) + "".join(f"[a{i}]" for i in range(nv)) + f"concat=n={nv}:v=0:a=1[outa]"
            fc = vchain + ";" + achain
        else:
            fc = vchain
        cmd += ["-filter_complex", fc, "-map", "[outv]", "-r", rate]
        if has_audio:
            cmd += ["-map", "[outa]"]
        else:
            cmd += ["-map", "1:a:0"]
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd.append(str(out))
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return

    if use_multi and use_tilt_title:
        v_parts: List[str] = []
        a_parts: List[str] = []
        for i, (ls, le) in enumerate(intr):
            v_parts.append(
                f"[0:v]trim=start={ls:.3f}:end={le:.3f},setpts=PTS-STARTPTS[v{i}];"
            )
        nv = len(intr)
        vconcat = "".join(f"[v{i}]" for i in range(nv)) + f"concat=n={nv}:v=1:a=0[vc];"
        if has_audio:
            for i, (ls, le) in enumerate(intr):
                a_parts.append(
                    f"[0:a]atrim=start={ls:.3f}:end={le:.3f},asetpts=PTS-STARTPTS[a{i}];"
                )
            achain = "".join(a_parts) + "".join(f"[a{i}]" for i in range(nv)) + f"concat=n={nv}:v=0:a=1[aud];"
        else:
            achain = ""
        middle = "".join(v_parts) + vconcat
        if has_audio:
            middle += achain
        tilt = _TITLE_TILT_RAD
        rw, rh = _TITLE_ROT_W, _TITLE_ROT_H
        middle += f"[vc]{vf_scale_pad}[bg];color=c=black@0:s=1080x1920:d={d_color}:r={rate},format=yuva420p,{title_chain},rotate={tilt}:fillcolor=black@0:ow={rw}:oh={rh}[tx];[bg][tx]overlay=(W-w)/2:(H-h)/2:format=auto[vout]"
        cmd += ["-filter_complex", middle, "-map", "[vout]", "-r", rate, "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"]
        if has_audio:
            cmd += ["-map", "[aud]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd.append(str(out))
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return

    # Single slice (no internal concat)
    if use_tilt_title:
        tilt = _TITLE_TILT_RAD
        rw, rh = _TITLE_ROT_W, _TITLE_ROT_H
        fc = (
            f"[0:v]{vf_scale_pad}[bg];"
            f"color=c=black@0:s=1080x1920:d={d_color}:r={rate},format=yuva420p,"
            f"{title_chain},rotate={tilt}:fillcolor=black@0:ow={rw}:oh={rh}[tx];"
            f"[bg][tx]overlay=(W-w)/2:(H-h)/2:format=auto[vout]"
        )
        cmd += [
            "-filter_complex",
            fc,
            "-map",
            "[vout]",
            "-r",
            rate,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        cmd += [
            "-vf",
            vf_scale_pad,
            "-r",
            rate,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]

    if has_audio:
        if not use_tilt_title:
            cmd += ["-map", "0:v:0"]
        cmd += [
            "-map",
            "0:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
        ]
    else:
        if not use_tilt_title:
            cmd += ["-map", "0:v:0"]
        cmd += [
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
        ]
    cmd.append(str(out))
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def ffmpeg_concat(parts: List[Path], final: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    lst = final.parent / "concat_list.txt"
    lines = [f"file '{p.absolute()}'" for p in parts]
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(final),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="Folder with video clips")
    ap.add_argument(
        "--limit",
        type=int,
        default=4,
        help="Max .MOV clips to analyze (0 = all); order by file creation time",
    )
    ap.add_argument(
        "--target",
        type=float,
        default=30.0,
        help="Soft duration (seconds). Default planning budget; with --flexible-duration, used as a loose floor hint for Grok while fill uses --max-total-sec.",
    )
    ap.add_argument(
        "--hard-cap-mult",
        type=float,
        default=1.1,
        help="With default mode: hard max = min(target×this, max-total-sec). Ignored when --flexible-duration (ceiling is max-total-sec only).",
    )
    ap.add_argument("--no-grok", action="store_true", help="Force local ranking only")
    ap.add_argument(
        "--no-analysis-cache",
        action="store_true",
        help="Always run Whisper/YOLO/enrichment; ignore uploads/analysis_cache/",
    )
    ap.add_argument(
        "--template",
        type=str,
        default="",
        help="Grok template: roast, roast_hot_chocolate, ... See story_prompts.py / docs/STORY_TEMPLATES.md",
    )
    ap.add_argument(
        "--title-line1",
        default=None,
        help="Override first title line (implies manual hook; empty string ok)",
    )
    ap.add_argument(
        "--title-line2",
        default=None,
        help="Override second title line (use with --title-line1 or alone)",
    )
    ap.add_argument(
        "--brand-line",
        default=DEFAULT_BRAND_LINE,
        help="Third overlay line under hook (default: Agroverse; use \"\" to clear)",
    )
    ap.add_argument(
        "--no-grok-overlay-title",
        action="store_true",
        help="Do not call Grok for opening hook; use first-clip transcript heuristic only",
    )
    ap.add_argument(
        "--out-suffix",
        type=str,
        default="",
        help="Append to generated folder name (e.g. 60s) so --target changes do not overwrite another render",
    )
    ap.add_argument(
        "--max-total-sec",
        type=float,
        default=120.0,
        help="Absolute ceiling on body duration after trim (default 120). With --flexible-duration, also the planning/top-up budget.",
    )
    ap.add_argument(
        "--flexible-duration",
        action="store_true",
        help="Let runtime follow the edit (MMR/Grok + padding) up to --max-total-sec; do not cluster around --target. Trim only if over max-total-sec.",
    )
    ap.add_argument(
        "--no-tighten-pauses",
        action="store_true",
        help="Disable inter-word dead-air tightening (Whisper word gaps) inside each extract",
    )
    ap.add_argument(
        "--title-max-width-frac",
        type=float,
        default=0.5,
        help="Max fraction of frame width (1080) for wrapped title lines (default 0.5)",
    )
    args = ap.parse_args()
    plan_budget = (
        float(args.max_total_sec)
        if args.flexible_duration
        else float(args.target)
    )

    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))

    folder: Path = args.folder.expanduser()
    if not folder.is_dir():
        print("Not a directory:", folder, file=sys.stderr)
        return 1

    movs = sorted(folder.glob("*.MOV")) + sorted(folder.glob("*.mov"))
    if not movs:
        print("No .MOV files in", folder, file=sys.stderr)
        return 1
    if args.limit and args.limit > 0:
        movs = movs[: args.limit]
    movs = sort_paths_by_creation_time(movs)

    if args.flexible_duration:
        print(
            f"Flexible duration: planning/top-up budget {plan_budget:.1f}s "
            f"(hard trim cap {float(args.max_total_sec):.1f}s; --target {args.target} is a loose floor hint)"
        )

    base_out = f"folder_short_{folder.name.replace(' ', '_')}"
    suf = (args.out_suffix or "").strip()
    if suf:
        safe = re.sub(r"[^\w\-.]+", "_", suf).strip("._-")
        if safe:
            base_out = f"{base_out}_{safe}"
    out_dir = root / "uploads" / "generated" / base_out
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Analyzing", len(movs), "clips (Whisper + YOLO + scene + motion)...")
    from video_analyzer import analyze_video
    from segment_enrichment import wrap_multivideo_for_grok

    enrich_flag = True
    analyses: List[Dict[str, Any]] = []
    for i, p in enumerate(movs):
        cpath = cache_json_path(root, p, enrich_flag)
        cached: Optional[Dict[str, Any]] = None
        if not args.no_analysis_cache:
            cached = load_cached_analysis(cpath, p, enrich_flag)
        if cached is not None:
            print(f"  [{i+1}/{len(movs)}] {p.name} (cached analysis)")
            analyses.append(cached)
            continue
        print(f"  [{i+1}/{len(movs)}] {p.name}")
        result = analyze_video(str(p), enrich_visual_dynamics=enrich_flag)
        analyses.append(result)
        if not args.no_analysis_cache:
            try:
                save_cached_analysis(cpath, p, enrich_flag, result)
            except OSError as e:
                print("Warning: could not write analysis cache:", e, file=sys.stderr)

    bundle = wrap_multivideo_for_grok(analyses)
    (out_dir / "analysis_bundle.json").write_text(
        json.dumps(bundle, indent=2, default=str), encoding="utf-8"
    )

    plan: Optional[Dict[str, Any]] = None
    if not args.no_grok:
        try:
            from grok_client import analyze_video_segments, get_grok_api_key

            if get_grok_api_key():
                from story_prompts import grok_prompts_for_template

                print("Calling Grok for editing plan...")
                tmpl = args.template.strip() or None
                if tmpl:
                    user_dir, extra_ctx = grok_prompts_for_template(tmpl)
                else:
                    user_dir = (
                        "Roasting cacao / chocolate with Mulan — cozy and authentic, not corporate. "
                        "Instagram Reels: favor moments that are funny OR inspire awe (laughter, surprise, "
                        "wonder, big reactions, satisfying milestones). Mix activities: roast, crack beans, "
                        "taste nibs, brew, sip hot chocolate, people commenting — avoid one-note repetition."
                    )
                    extra_ctx = None
                if args.flexible_duration:
                    td_min = int(
                        max(
                            15,
                            min(
                                float(args.target) * 0.5,
                                float(args.max_total_sec) * 0.35,
                            ),
                        )
                    )
                    td_max = int(float(args.max_total_sec))
                else:
                    td_min = int(max(15, args.target - 5))
                    td_max = int(
                        min(float(args.target) + 5.0, float(args.max_total_sec))
                    )
                if td_min > td_max:
                    td_min = td_max
                plan = analyze_video_segments(
                    bundle,
                    target_duration_min=td_min,
                    target_duration_max=td_max,
                    user_direction=user_dir,
                    additional_context=extra_ctx,
                )
                (out_dir / "grok_plan.json").write_text(
                    json.dumps(plan, indent=2, default=str), encoding="utf-8"
                )
            else:
                print("No GROK_API_KEY; using local editor_score ranking.")
        except Exception as e:
            print("Grok failed:", e, "; using local rank.")
    # Title is drawn on the first video segment (no separate title card); full target is body.
    title_s = 0.0
    body_budget = max(5.0, plan_budget - title_s)
    # Short on-screen time: large type + tight copy; avoid long burns that expose clipping.
    title_on_first_sec = min(
        1.85, max(1.05, min(plan_budget, 90.0) * 0.052)
    )

    if plan is None:
        plan = local_editing_plan(analyses, target_seconds=plan_budget)
        (out_dir / "local_plan.json").write_text(
            json.dumps(plan, indent=2, default=str), encoding="utf-8"
        )
    else:
        ep0 = plan.get("editing_plan") or {}
        if _editing_plan_body_seconds(ep0) < body_budget - 2.0:
            print("Editing plan body under target; topping up with local rank + timeline fill.")
            plan = local_editing_plan(
                analyses,
                target_seconds=plan_budget,
                seed_from_editing_plan=ep0,
                metadata_override=plan.get("metadata"),
            )
            (out_dir / "plan_topped_up.json").write_text(
                json.dumps(plan, indent=2, default=str), encoding="utf-8"
            )

    path_by_file = {a["file"]: a["path"] for a in analyses}
    analyses_by_file = {a["file"]: a for a in analyses}

    print("Reordering edit to file creation time (forward-moving story)...")
    reorder_plan_chronologically(plan, path_by_file)
    print("Applying speech tail padding (0.5–1.0s, filler/pause guarded)...")
    apply_tail_padding_to_plan(plan, analyses_by_file, path_by_file)
    if args.flexible_duration:
        cap_body = float(args.max_total_sec)
    else:
        cap_body = min(
            float(args.target) * float(args.hard_cap_mult),
            float(args.max_total_sec),
        )
    print(
        f"Trimming to hard cap {cap_body:.2f}s (max_total_sec={args.max_total_sec}) if needed..."
    )
    trim_plan_to_duration_ceiling(plan, cap_body)

    ep = plan.get("editing_plan") or {}
    segs = ep.get("selected_segments") or []
    order = ep.get("sequence") or [s.get("segment_id") for s in segs]
    by_id = {s.get("segment_id"): s for s in segs}
    (out_dir / "plan_for_render.json").write_text(
        json.dumps(plan, indent=2, default=str), encoding="utf-8"
    )

    parts: List[Path] = []
    first_clip_done = False

    first_spec: Optional[Dict[str, Any]] = None
    for sid in order:
        sp0 = by_id.get(sid)
        if sp0:
            first_spec = sp0
            break

    title_tuple: Optional[Tuple[str, str, str]] = None
    if first_spec is not None:
        brand = (args.brand_line or "").strip()
        if args.title_line1 is not None or args.title_line2 is not None:
            t1 = (args.title_line1 if args.title_line1 is not None else "").strip()
            t2 = (args.title_line2 if args.title_line2 is not None else "").strip()
            title_tuple = (t1, t2, brand)
            print(f"Title overlay (manual): {t1!r} / {t2!r} — {brand!r}")
        else:
            used_grok = False
            blob = build_full_transcript_context(analyses)
            tr0 = first_spec.get("time_range") or {}
            vf0 = str(first_spec.get("video_file") or "")
            an0 = analyses_by_file.get(vf0)
            open_snip = ""
            if an0:
                open_snip = collect_transcript_in_window(
                    an0,
                    float(tr0.get("start", 0)),
                    float(tr0.get("end", 0)),
                )
            tmpl = (args.template or "").strip()
            hint = f"User template keyword: {tmpl}. Match arc when possible." if tmpl else ""
            if (
                not args.no_grok_overlay_title
                and get_grok_api_key()
                and blob.strip()
            ):
                try:
                    got = grok_overlay_title_lines(
                        blob, open_snip, template_hint=hint
                    )
                    if got:
                        gl1, gl2, ang = got
                        title_tuple = (gl1, gl2, brand)
                        used_grok = True
                        (out_dir / "grok_overlay_title.json").write_text(
                            json.dumps(
                                {"line1": gl1, "line2": gl2, "angle": ang},
                                indent=2,
                                ensure_ascii=False,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        print(
                            f"Title overlay (Grok, {ang}): {gl1!r} / {gl2!r} — {brand!r}"
                        )
                except Exception as e:
                    print(
                        "Grok overlay title failed:",
                        e,
                        "; using first-clip transcript fallback.",
                        file=sys.stderr,
                    )
            if not used_grok:
                l1, l2 = overlay_lines_from_first_clip(first_spec, analyses_by_file)
                title_tuple = (l1, l2, brand)
                print(f"Title overlay (transcript fallback): {l1!r} / {l2!r} — {brand!r}")

    for idx, sid in enumerate(order, start=1):
        spec = by_id.get(sid)
        if not spec:
            continue
        vf = spec.get("video_file")
        src = Path(path_by_file.get(vf) or "")
        if not src.is_file():
            print("Missing source for", vf, file=sys.stderr)
            continue
        tr = spec.get("time_range") or {}
        start = float(tr.get("start", 0))
        end = float(tr.get("end", start + 3))
        dur = max(0.1, end - start)
        outp = out_dir / f"part_{idx:02d}_{sid}.mp4"
        overlay: Optional[float] = None
        use_title_lines: Optional[Tuple[str, str, str]] = None
        if not first_clip_done:
            overlay = min(title_on_first_sec, max(0.95, dur * 0.17))
            use_title_lines = title_tuple
            first_clip_done = True
        loc_iv: Optional[List[Tuple[float, float]]] = None
        if not args.no_tighten_pauses:
            an_i = analyses_by_file.get(str(vf))
            if an_i:
                loc_iv = local_keep_intervals_simple(an_i, start, end)
        print(f"  extract {vf} {start:.1f}-{end:.1f}s -> {outp.name}")
        ffmpeg_extract_letterbox(
            src,
            start,
            dur,
            outp,
            title_overlay_sec=overlay,
            title_lines=use_title_lines,
            local_intervals=loc_iv,
            title_max_width_frac=float(args.title_max_width_frac),
        )
        parts.append(outp)

    final = out_dir / "short_final.mp4"
    print("Concat ->", final)
    ffmpeg_concat(parts, final)

    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "/usr/local/bin/ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(final),
        ],
        capture_output=True,
        text=True,
    )
    print("Done. Duration:", probe.stdout.strip(), "s")
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
