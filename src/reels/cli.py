"""Command dispatcher for the ``reels`` CLI.

Threads the SPEC's design rules through every command: strong defaults,
``--json`` on every command, ``--dry-run`` where defined, a documented
exit-code taxonomy (errors.py), and no interactive prompts. Every subcommand
handler is ``cmd_<name>(args) -> int`` reachable from ``main``.

This module owns *dispatch*: the bodies for capture / verify / edit / prove /
render are implemented in their own modules by later units and wired in here
via the ``_HANDLERS`` registry. Until then they stub to exit 70 (not
implemented).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .errors import Exit, ExitCodes
from .identify import content_id


# --------------------------------------------------------------------------
# Handler plumbing
# --------------------------------------------------------------------------

# Registered lazily: subcommand name -> callable(args, cfg) -> int.
_HANDLERS: dict[str, Callable[..., int]] = {}


def register(name: str, handler: Callable[..., int]) -> None:
    """Register a command handler (used by later units to wire in bodies)."""
    _HANDLERS[name] = handler


def _inventory(root: Path) -> dict:
    """Scan ``root`` for capture documents, reel documents, and media.

    Returns a plain dict suitable for ``--json`` output.
    """
    root = root.resolve()
    captures: list[dict] = []
    reels: list[dict] = []
    for p in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            if payload.get("schema_version") and "captured" in payload:
                captures.append(
                    {"path": str(p), "capture_id": payload.get("capture_id")}
                )
            elif payload.get("schema_version") and "clips" in payload:
                reels.append({"path": str(p), "reel_id": payload.get("reel_id")})
    media = sorted(
        str(p) for p in root.rglob("*")
        if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    )
    return {"root": str(root), "captures": captures, "reels": reels, "media": media}


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    inv = _inventory(Path(args.root))
    if args.json:
        print(json.dumps(inv, indent=2, default=str))
    else:
        print(f"Captures ({len(inv['captures'])}):")
        for c in inv["captures"]:
            print(f"  {c['path']}")
        print(f"Reels ({len(inv['reels'])}):")
        for r in inv["reels"]:
            print(f"  {r['path']}")
        print(f"Media ({len(inv['media'])}):")
        for m in inv["media"]:
            print(f"  {m}")
    return ExitCodes.OK


def cmd_id(args: argparse.Namespace) -> int:
    cid = content_id(Path(args.path))
    if args.json:
        print(json.dumps({"path": str(args.path), "id": cid}))
    else:
        print(cid)
    return ExitCodes.OK


# Stubs for commands whose bodies arrive in later units. They return the
# "not implemented" sentinel (70) so an agent never mistakes a stub for work.
def _stub(args: argparse.Namespace) -> int:
    return ExitCodes.NOT_IMPLEMENTED


# Unit 01 commands (inventory / identity) are implemented here; later units
# register capture/verify/edit/prove/render handlers via register().
register("list", cmd_list)
register("id", cmd_id)


# --------------------------------------------------------------------------
# Argument surface
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reels",
        description="LUFS-family screen-capture & reel primitive.",
    )
    parser.add_argument(
        "--version", action="version", version=f"reels {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def _json(ap: argparse.ArgumentParser) -> None:
        ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    # capture
    p_cap = sub.add_parser("capture", help="record a screen/window shot -> media + capture.json")
    p_cap.add_argument("--out", default="./shots", help="output directory")
    p_cap.add_argument("--name", default="shot", help="capture label")
    p_cap.add_argument("--region", default="monitor:0", help="WxH+X+Y | monitor:N | window:<id>")
    p_cap.add_argument("--fps", type=int, default=30)
    p_cap.add_argument("--audio", action="store_true", help="capture system audio")
    p_cap.add_argument("--mic", action="store_true", help="capture microphone")
    p_cap.add_argument("--duration", type=float, default=None, help="seconds")
    p_cap.add_argument("--codec", default="h264")
    p_cap.add_argument("--dry-run", action="store_true")
    _json(p_cap)

    # verify
    p_ver = sub.add_parser("verify", help="contract one: is the capture whole?")
    p_ver.add_argument("dir", help="directory containing a capture.json")
    p_ver.add_argument("--json", action="store_true")
    p_ver.add_argument("--dry-run", action="store_true", help="gather facts, don't decide")

    # edit
    p_ed = sub.add_parser("edit", help="author a reel.json from verified captures")
    p_ed.add_argument("--add", action="append", default=[], help="capture_ref to add (repeatable)")
    p_ed.add_argument("--order", type=int, default=None)
    p_ed.add_argument("--trim-in", dest="trim_in", type=float, default=None)
    p_ed.add_argument("--trim-out", dest="trim_out", type=float, default=None)
    p_ed.add_argument("--overlay-text", dest="overlay_text", default=None)
    p_ed.add_argument("--captures", default=".", help="root dir to resolve capture documents from")
    p_ed.add_argument("--out", default="reel.json")
    p_ed.add_argument("--dry-run", action="store_true")
    _json(p_ed)

    # prove
    p_pr = sub.add_parser("prove", help="contract two: did the assembly behave as asked?")
    p_pr.add_argument("reel", help="path to reel.json")
    p_pr.add_argument("--json", action="store_true")
    p_pr.add_argument("--dry-run", action="store_true", help="skip the deterministic render")

    # render
    p_rd = sub.add_parser("render", help="ffmpeg render a reel.json -> output file")
    p_rd.add_argument("reel", help="path to reel.json")
    p_rd.add_argument("--out", default=None, help="output file path")
    p_rd.add_argument("--captures", default=".", help="root dir to resolve capture media from")
    p_rd.add_argument("--dry-run", action="store_true")
    _json(p_rd)

    # list
    p_ls = sub.add_parser("list", help="inventory captures/reels under a root")
    p_ls.add_argument("root", nargs="?", default=".", help="root directory to scan")
    _json(p_ls)

    # id
    p_id = sub.add_parser("id", help="deterministic content identity (reel-<hex>)")
    p_id.add_argument("path", help="file to identify")
    _json(p_id)

    return parser


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

def _dispatch(name: str, args: argparse.Namespace) -> int:
    handler = _HANDLERS.get(name, _stub)
    return handler(args)


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return ExitCodes.USAGE

    try:
        return _dispatch(args.command, args)
    except Exit as exc:
        if exc.message:
            print(f"reels: {exc.message}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return ExitCodes.INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------
# Real command bodies (later units) wire themselves in on import. Unimplemented
# commands are not registered here, so they fall back to the exit-70 stub.
# --------------------------------------------------------------------------

def _load_command_bodies() -> None:
    from . import capture  # noqa: F401  (capture)
    from . import edit  # noqa: F401  (edit)
    from . import render  # noqa: F401  (render)
    from .contracts import verify  # noqa: F401  (verify)

_load_command_bodies()
