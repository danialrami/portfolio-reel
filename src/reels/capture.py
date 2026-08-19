"""Headless screen capture -> media + capture.json (reels capture).

Drives the detected platform adapter, writes a media file and a normalized
Capture Document, handles SIGINT by leaving a partial file with an
``unverifiable`` verdict (exit 6), and supports ``--dry-run`` / ``--json``
with no interactive prompts.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import adapters as _adapters
from .adapters import Adapter, CaptureRequest
from .capture_doc import (
    UNVERIFIABLE,
    Check,
    Captured,
    Capture,
    Requested,
    Source,
    Verification,
    save_capture,
)
from .errors import Exit, ExitCodes


@dataclass
class CaptureResult:
    capture: Capture
    command: list[str]
    media_path: Path | None = None
    aborted: bool = False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_capture(
    adapter: Adapter, req: CaptureRequest, media_path: Path, aborted: bool
) -> Capture:
    c = Capture()
    c.capture_id = "rec-" + _sha256(media_path)[:8]
    c.created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c.source = Source(platform=adapter.platform, tool=adapter.tool, region=req.region)
    c.requested = Requested(
        fps=req.fps, codec=req.codec, audio=req.audio, mic=req.mic, out=req.out
    )
    c.captured = Captured()  # facts are computed later by `reels verify`
    c.file = media_path.name
    c.content_sha256 = _sha256(media_path)
    c.verification = Verification(
        verdict=UNVERIFIABLE,
        checks=[
            Check(name="parses_clean", ok=True),
            Check(name="media_present", ok=media_path.exists()),
        ],
    )
    return c


def run_capture(req: CaptureRequest, dry_run: bool = False) -> CaptureResult:
    if req.audio or req.mic:
        raise Exit(
            ExitCodes.NOT_IMPLEMENTED,
            "audio capture is deferred to a later verified audio phase",
        )
    adapter = _adapters.detect()  # raises Exit(3) when no supported source
    cmd = adapter.build_command(req)

    out_dir = Path(req.out)
    os.makedirs(out_dir, exist_ok=True)

    # Adapter commands return a basename as their final output argument. Resolve
    # it into the requested directory before launching the process; otherwise a
    # successful adapter writes into the agent's cwd while the document builder
    # looks under --out and fails to hash the media.
    media_path = out_dir / Path(cmd[-1]).name
    cmd[-1] = str(media_path)

    if dry_run:
        c = Capture()
        c.capture_id = "rec-dryrun"
        c.created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        c.source = adapter.source_block()
        c.requested = Requested(
            fps=req.fps, codec=req.codec, audio=req.audio, mic=req.mic, out=req.out
        )
        c.verification.verdict = UNVERIFIABLE
        return CaptureResult(capture=c, command=cmd, media_path=None, aborted=False)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    aborted = False
    try:
        if req.duration:
            try:
                deadline = time.monotonic() + req.duration
                while time.monotonic() < deadline and proc.poll() is None:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                aborted = True
        else:
            try:
                while proc.poll() is None:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                aborted = True
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    if not media_path.exists():
        raise Exit(
            ExitCodes.SOURCE,
            f"capture command produced no media at {media_path}",
        )

    c = _build_capture(adapter, req, media_path, aborted)
    if aborted:
        c.verification.verdict = UNVERIFIABLE
    save_capture(out_dir / "capture.json", c)
    return CaptureResult(capture=c, command=cmd, media_path=media_path, aborted=aborted)


def cmd_capture(args) -> int:
    req = CaptureRequest(
        region=args.region,
        fps=args.fps,
        # Audio remains a document-level extension point but is not exposed or
        # requested by the phase-0/1 CLI.
        duration=args.duration,
        codec=args.codec,
        out=args.out,
        name=args.name,
    )
    result = run_capture(req, dry_run=args.dry_run)

    if args.dry_run:
        payload = {
            "dry_run": True,
            "platform": result.capture.source.platform,
            "tool": result.capture.source.tool,
            "region": req.region,
            "command": result.command,
            "out": str(Path(req.out) / (Path(result.command[-1]).name)),
            "wrote_media": False,
        }
        print(json.dumps(payload, indent=2) if args.json else _fmt(payload))
        return ExitCodes.OK

    from .capture_doc import to_json

    if result.aborted:
        print(
            json.dumps({"status": "interrupted", "verdict": UNVERIFIABLE,
                        "media": str(result.media_path)})
            if args.json
            else f"capture interrupted (partial media, verdict={UNVERIFIABLE})"
        )
        return ExitCodes.INTERRUPTED

    if args.json:
        print(to_json(result.capture))
    else:
        print(f"captured {result.media_path} as {result.capture.capture_id}")
    return ExitCodes.OK


def _fmt(payload: dict) -> str:
    lines = [f"platform:  {payload['platform']}", f"tool:      {payload['tool']}",
             f"region:    {payload['region']}"]
    lines.append("command:   " + " ".join(payload["command"]))
    lines.append(f"out:       {payload['out']}")
    return "\n".join(lines)


from .cli import register  # noqa: E402

register("capture", cmd_capture)
