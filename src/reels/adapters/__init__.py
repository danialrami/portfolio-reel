"""Platform capture adapters.

ffmpeg is the single cross-platform engine; thin adapters pick the concrete
capture tool per platform:

- Linux X11                -> ``ffmpeg -f x11grab``
- Linux wlroots Wayland    -> ``wl-screenrec`` (preferred, HW encode) or
                              ``wf-recorder``
- macOS                    -> ``ffmpeg -f avfoundation``
- Windows                  -> ``ffmpeg -f gdigrab``

No obs-cli / OBS anywhere. Detection is environment- and tool-driven and is
injectable (``env`` / ``which``) so tests can simulate each platform.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass
from typing import Callable

from ..errors import Exit, ExitCodes

_REGION = re.compile(r"^(\d+)x(\d+)(?:\+(\d+)\+(\d+))?$")


@dataclass
class CaptureRequest:
    region: str = "monitor:0"
    fps: int = 30
    audio: bool = False
    mic: bool = False
    duration: float | None = None
    codec: str = "h264"
    out: str = "./shots"
    name: str = "shot"


@dataclass
class Adapter:
    platform: str            # wayland | x11 | mac | win
    tool: str                # wl-screenrec | wf-recorder | ffmpeg:...
    build_command: Callable[[CaptureRequest], list[str]]

    def source_block(self) -> dict:
        return {"platform": self.platform, "tool": self.tool}


def _geometry(region: str) -> tuple[str | None, str | None]:
    """Return ``(geom, mode)`` for a region string.

    geom is ``WxH+X+Y`` (or ``WxH``) for explicit geometry; ``None`` when the
    region is a monitor or window spec (handled per adapter). Raises Exit(3)
    on an unparseable region.
    """
    if region.startswith("monitor:"):
        idx = region.split(":", 1)[1]
        if not idx.isdigit():
            raise Exit(ExitCodes.SOURCE, f"bad monitor index in region {region!r}")
        return None, f"monitor:{idx}"
    if region.startswith("window:"):
        return None, "window"
    m = _REGION.match(region)
    if not m:
        raise Exit(ExitCodes.SOURCE, f"cannot parse region {region!r}")
    w, h, x, y = m.group(1), m.group(2), m.group(3) or "0", m.group(4) or "0"
    return f"{w}x{h}+{x}+{y}", "geometry"


def detect(env=None, which=None) -> Adapter:
    env = env or os.environ
    which = which or shutil.which
    system = platform.system()

    if env.get("WAYLAND_DISPLAY"):
        tool = None
        if which("wl-screenrec"):
            tool = "wl-screenrec"
        elif which("wf-recorder"):
            tool = "wf-recorder"
        else:
            tool = "wl-screenrec"  # preferred; command builds regardless
        return Adapter(
            "wayland",
            tool,
            lambda req, selected_tool=tool: _build_wayland(req, selected_tool),
        )

    if env.get("DISPLAY"):
        return Adapter("x11", "ffmpeg:x11grab", _build_x11)

    if system == "Darwin":
        return Adapter("mac", "ffmpeg:avfoundation", _build_mac)
    if system == "Windows":
        return Adapter("win", "ffmpeg:gdigrab", _build_win)

    raise Exit(ExitCodes.SOURCE, "no supported capture source detected (need Wayland or X11)")


def _media_path(req: CaptureRequest) -> str:
    from datetime import datetime, timezone
    import re as _re

    label = _re.sub(r"[^A-Za-z0-9_.-]+", "_", req.name) or "shot"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{label}.mp4"


def _build_x11(req: CaptureRequest) -> list[str]:
    geom, mode = _geometry(req.region)
    if mode == "window":
        raise Exit(ExitCodes.SOURCE, "window capture is not supported on X11 x11grab; use a monitor or geometry region")
    display = mode.split(":")[1] if mode.startswith("monitor:") else "0"
    cmd = ["ffmpeg", "-y", "-f", "x11grab", "-framerate", str(req.fps)]
    if geom:
        cmd += ["-video_size", geom.split("+")[0], "-i", f":{display}+{geom.split('+', 1)[1]}"]
    else:
        cmd += ["-i", f":{display}"]
    if req.duration:
        cmd += ["-t", str(req.duration)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", _media_path(req)]
    return cmd


def _build_wayland(req: CaptureRequest, tool: str = "wl-screenrec") -> list[str]:
    geom, mode = _geometry(req.region)
    # Audio capture is deliberately deferred. Keep the request fields in the
    # document shape for a later audio phase, but never silently add an audio
    # stream to a phase-0/1 recording.
    if geom:
        args = ["--geometry", geom]
    elif mode == "window":
        raise Exit(ExitCodes.SOURCE, "window capture needs the tool's picker; use monitor or geometry")
    else:  # monitor:N
        n = mode.split(":")[1]
        args = ["--monitor", n]
    args += ["--fps", str(req.fps), "--output-file", _media_path(req)]
    if req.duration:
        args += ["--duration", str(req.duration)]
    return [tool, *args]


def _build_mac(req: CaptureRequest) -> list[str]:
    geom, mode = _geometry(req.region)
    # Audio input selection is reserved for the later audio phase. `none`
    # makes the current recording contract video-only even if a caller passes
    # the future CaptureRequest fields programmatically.
    aud = "none"
    device = f"{mode.split(':')[1] if mode else '0'}:{aud}"
    cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-framerate", str(req.fps),
           "-i", device]
    if req.duration:
        cmd += ["-t", str(req.duration)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", _media_path(req)]
    return cmd


def _build_win(req: CaptureRequest) -> list[str]:
    geom, mode = _geometry(req.region)
    cmd = ["ffmpeg", "-y", "-f", "gdigrab", "-framerate", str(req.fps)]
    if geom:
        cmd += ["-video_size", geom.split("+")[0], "-offset_x", geom.split("+")[1].split("+")[0],
                "-offset_y", geom.split("+")[2] if "+" in geom.split("+",1)[1] else "0", "-i", "desktop"]
    else:
        cmd += ["-i", "desktop"]
    if req.duration:
        cmd += ["-t", str(req.duration)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", _media_path(req)]
    return cmd


def probe_sources(env=None, which=None) -> list[dict]:
    """Best-effort list of capturable sources for the detected platform."""
    try:
        adapter = detect(env=env, which=which)
    except Exit:
        return []
    sources = [{"platform": adapter.platform, "tool": adapter.tool}]
    if adapter.platform in {"x11", "wayland"}:
        sources.append({"region": "monitor:0"})
        sources.append({"region": "window:<id>"})
    return sources
