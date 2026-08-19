"""Exit-code taxonomy and the exception that carries a process exit code.

Every command returns one of these codes (docs/SPEC.md). The taxonomy is the
public contract for agents and scripts driving ``reels`` headlessly.
"""

from __future__ import annotations


class ExitCodes:
    """The SPEC exit-code taxonomy."""

    OK = 0                      # success (captured+verified / proved / rendered)
    USAGE = 2                   # usage / bad args
    SOURCE = 3                  # capture source (region/device) unavailable
    MISSING_BINARY = 4          # required binary missing (ffmpeg / ffprobe / tool)
    VIOLATED = 5                # contract violated
    INTERRUPTED = 6             # interrupted before a valid output
    UNVERIFIABLE = 7            # contract unverifiable (couldn't evaluate)
    NOT_IMPLEMENTED = 70        # honest-failure sentinel for stubbed commands


# Convenience mapping mirror (names exactly as in the taxonomy table).
EXIT = {
    "ok": ExitCodes.OK,
    "usage": ExitCodes.USAGE,
    "source": ExitCodes.SOURCE,
    "missing_binary": ExitCodes.MISSING_BINARY,
    "violated": ExitCodes.VIOLATED,
    "interrupted": ExitCodes.INTERRUPTED,
    "unverifiable": ExitCodes.UNVERIFIABLE,
    "not_implemented": ExitCodes.NOT_IMPLEMENTED,
}


class Exit(Exception):
    """Raise to terminate the CLI with a taxonomy exit code.

    ``code`` is one of the ``ExitCodes`` constants; ``message`` (optional) is
    printed to stderr before exiting.
    """

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
