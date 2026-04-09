#!/usr/bin/env python3
"""
Analyze clips in a folder (Whisper + YOLO + scene + motion), rank via Grok or
local MMR selection (diverse + humor/awe hooks), render ~30s 9:16 letterboxed short.

Keeps source audio (AAC in output). Title is overlaid on the first clip
(yellow / outline / purple shadow, Arial Rounded on macOS), not a separate
solid-color card.

Usage:
  ./venv/bin/python build_short_from_folder.py /path/to/folder [--limit 4] [--target 30]

Requires: ffmpeg, venv deps (whisper, ultralytics, opencv optional).
Grok optional: GROK_API_KEY in .env
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clip_postprocess import (
    apply_tail_padding_to_plan,
    reorder_plan_chronologically,
    sort_paths_by_creation_time,
    trim_plan_to_duration_ceiling,
)
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


def _title_overlay_drawfilters(overlay_sec: float) -> str:
    """Stacked drawtext filters: yellow + outline + purple shadow (reference short style)."""
    en = f"between(t\\,0\\,{overlay_sec:.3f})"
    font = _default_rounded_title_font()
    font_opt = ""
    if font:
        font_opt = f":fontfile={_escape_drawtext_fontfile(font)}"
    # Reference: heavy rounded sans, yellow face, dark outline, purple extrusion shadow.
    line1 = "Roasting chocolate"
    line2 = "with Mulan"
    sub = "Agroverse"
    shadow = ":shadowx=6:shadowy=9:shadowcolor=0x5E35B1"
    outline = ":borderw=4:bordercolor=black"
    d1 = (
        f"drawtext=text='{line1}'{font_opt}:fontsize=64:fontcolor=#FFDD00{outline}{shadow}"
        f":x=(w-text_w)/2:y=h*0.50:enable='{en}'"
    )
    d2 = (
        f"drawtext=text='{line2}'{font_opt}:fontsize=64:fontcolor=#FFDD00{outline}{shadow}"
        f":x=(w-text_w)/2:y=h*0.50+78:enable='{en}'"
    )
    d3 = (
        f"drawtext=text='{sub}'{font_opt}:fontsize=34:fontcolor=#FFFFFF:borderw=2"
        f":bordercolor=black:shadowx=3:shadowy=4:shadowcolor=0x333333"
        f":x=(w-text_w)/2:y=h*0.50+160:enable='{en}'"
    )
    return ",".join([d1, d2, d3])


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
) -> None:
    """Extract segment, letterbox to 1080x1920, keep audio as AAC when present."""
    ffmpeg = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    vf_base = (
        "scale=1080:-2:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x1a1512,format=yuv420p"
    )
    if title_overlay_sec and title_overlay_sec > 0:
        vf = vf_base + "," + _title_overlay_drawfilters(title_overlay_sec)
    else:
        vf = vf_base

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
    cmd += [
        "-vf",
        vf,
        "-r",
        "30000/1001",
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
        cmd += [
            "-map",
            "0:v:0",
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
        cmd += [
            "-map",
            "0:v:0",
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
    ap.add_argument("--target", type=float, default=30.0, help="Target duration seconds (soft)")
    ap.add_argument(
        "--hard-cap-mult",
        type=float,
        default=1.1,
        help="Hard max total body duration = target * this (default 1.1 → 33s for 30s target)",
    )
    ap.add_argument("--no-grok", action="store_true", help="Force local ranking only")
    ap.add_argument(
        "--template",
        type=str,
        default="",
        help="Grok template: roast, roast_hot_chocolate, ... See story_prompts.py / docs/STORY_TEMPLATES.md",
    )
    args = ap.parse_args()

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

    out_dir = root / "uploads" / "generated" / f"folder_short_{folder.name.replace(' ', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Analyzing", len(movs), "clips (Whisper + YOLO + scene + motion)...")
    from video_analyzer import analyze_video
    from segment_enrichment import wrap_multivideo_for_grok

    analyses: List[Dict[str, Any]] = []
    for i, p in enumerate(movs):
        print(f"  [{i+1}/{len(movs)}] {p.name}")
        analyses.append(analyze_video(str(p), enrich_visual_dynamics=True))

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
                plan = analyze_video_segments(
                    bundle,
                    target_duration_min=int(max(15, args.target - 5)),
                    target_duration_max=int(args.target + 5),
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
    body_budget = max(5.0, float(args.target) - title_s)
    title_on_first_sec = min(3.0, float(args.target) * 0.12)

    if plan is None:
        plan = local_editing_plan(analyses, target_seconds=args.target)
        (out_dir / "local_plan.json").write_text(
            json.dumps(plan, indent=2, default=str), encoding="utf-8"
        )
    else:
        ep0 = plan.get("editing_plan") or {}
        if _editing_plan_body_seconds(ep0) < body_budget - 2.0:
            print("Editing plan body under target; topping up with local rank + timeline fill.")
            plan = local_editing_plan(
                analyses,
                target_seconds=args.target,
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
    cap_body = float(args.target) * float(args.hard_cap_mult)
    print(f"Trimming to hard cap {cap_body:.2f}s if needed...")
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
        if not first_clip_done:
            overlay = min(title_on_first_sec, max(1.5, dur * 0.35))
            first_clip_done = True
        print(f"  extract {vf} {start:.1f}-{end:.1f}s -> {outp.name}")
        ffmpeg_extract_letterbox(src, start, dur, outp, title_overlay_sec=overlay)
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
