"""Reel authoring: turn verified captures into a Reel Document (reels edit).

Authoring is headless and refuses to include a capture whose verification
verdict is not ``verified`` (exit 5 with a warning) — an agent can only
assemble reels from takes that passed Contract one.

Only *verified* captures are editable. Resolution happens against capture.json
documents discovered under a root directory by capture_id.
"""

from __future__ import annotations

import json
from pathlib import Path

from .capture_doc import VERIFIED, Capture, load_capture
from .errors import Exit, ExitCodes
from .reel_doc import (
    ClipRef,
    IntroOutro,
    Music,
    Output,
    Overlay,
    Reel,
    Style,
    save_reel,
    _compute_reel_id,
)


def find_capture(root: Path, capture_ref: str) -> Capture | None:
    """Find a capture document by capture_id under ``root``."""
    root = Path(root)
    for p in sorted(root.rglob("capture.json")) + sorted(root.rglob("*.capture.json")):
        try:
            c = load_capture(p)
        except (OSError, ValueError):
            continue
        if c.capture_id == capture_ref:
            return c
    return None


def author(
    clips: list[ClipRef],
    *,
    output: Output | None = None,
    style: Style | None = None,
    intro: IntroOutro | None = None,
    outro: IntroOutro | None = None,
    music: Music | None = None,
) -> Reel:
    """Build a schema-valid Reel from clip references, sorted by order.

    Every default is made explicit here (never implicit): output/style/intro/
    outro/music fall back to the dataclass defaults, which mirror the SPEC.
    """
    ordered = sorted(clips, key=lambda c: c.order)
    reel = Reel()
    if output:
        reel.output = output
    if style:
        reel.style = style
    if intro:
        reel.intro = intro
    if outro:
        reel.outro = outro
    if music:
        reel.music = music
    reel.clips = ordered
    reel.reel_id = _compute_reel_id(reel)
    return reel


def cmd_edit(args) -> int:
    refs = list(args.add or [])
    clips: list[ClipRef] = []
    root = Path(getattr(args, "captures", "."))

    for i, ref in enumerate(refs):
        cap = find_capture(root, ref)
        if cap is None:
            raise Exit(ExitCodes.VIOLATED, f"capture {ref!r} not found under {root}")
        if cap.verification.verdict != VERIFIED:
            raise Exit(
                ExitCodes.VIOLATED,
                f"capture {ref!r} is not verified (verdict={cap.verification.verdict}); "
                f"run `reels verify` first — refusing to edit",
            )
        order = (args.order or 1) + i
        clips.append(
            ClipRef(
                capture_ref=ref,
                order=order,
                trim_in=args.trim_in or 0.0,
                trim_out=args.trim_out or 0.0,
                overlay=Overlay(text=args.overlay_text or "", position="bottom-left"),
            )
        )

    reel = author(clips)

    import reels.reel_doc as rd

    if args.dry_run:
        if args.json:
            print(rd.to_json(reel))
        else:
            print(f"[dry-run] would write {'reel.json' if not getattr(args,'out',None) else args.out}")
        return ExitCodes.OK

    out = Path(args.out)
    save_reel(out, reel)
    print(f"wrote {out} ({len(reel.clips)} clips)")
    if args.json:
        import reels.reel_doc as rd2
        print(rd2.to_json(reel))
    return ExitCodes.OK


from .cli import register  # noqa: E402

register("edit", cmd_edit)
