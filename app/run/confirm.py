from __future__ import annotations

import os
import re
import select
import sys
import time

YES_RE = re.compile(r"\b(y|yes|yeah|yep|sure|ok|okay|confirm)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(n|no|nope|cancel|stop|abort|never)\b", re.IGNORECASE)

# Human confirmation must answer within this window or the run fails.
CONFIRM_TIMEOUT_SEC = 15.0

# Set by CLI --yes / --no (or ATLAS_AUTO_CONFIRM=yes|no).
AUTO_CONFIRM_ENV = "ATLAS_AUTO_CONFIRM"


class ConfirmationTimeout(Exception):
    """Raised when the operator does not answer yes/no in time."""


def auto_confirm_reply() -> bool | None:
    """Return True/False when auto-confirm is armed, else None for interactive."""
    raw = (os.getenv(AUTO_CONFIRM_ENV) or "").strip().lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def ask_yes_no(prompt: str, timeout_sec: float = CONFIRM_TIMEOUT_SEC) -> bool:
    """
    Ask for yes/no with a hard timeout.

    Returns True on yes, False on no.
    Raises ConfirmationTimeout if no answer within timeout_sec.
    When ATLAS_AUTO_CONFIRM is yes/no (CLI --yes / --no), skips the interactive prompt.
    """
    auto = auto_confirm_reply()
    if auto is not None:
        answer = "yes" if auto else "no"
        print(prompt, end="", flush=True)
        print(f"(auto {answer}) {answer}", flush=True)
        return auto

    print(prompt, end="", flush=True)
    print(f"(answer within {int(timeout_sec)}s) ", end="", flush=True)
    deadline = time.monotonic() + timeout_sec

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print()
            raise ConfirmationTimeout(
                "Human did not confirm: confirmation timed out after "
                f"{int(timeout_sec)} seconds."
            )
        ready, _, _ = select.select([sys.stdin], [], [], remaining)
        if not ready:
            print()
            raise ConfirmationTimeout(
                "Human did not confirm: confirmation timed out after "
                f"{int(timeout_sec)} seconds."
            )
        try:
            reply = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            print()
            raise ConfirmationTimeout("Human did not confirm.") from None
        if reply is None or reply == "":
            raise ConfirmationTimeout("Human did not confirm.")
        text = reply.strip()
        if not text:
            raise ConfirmationTimeout("Human did not confirm.")
        # Echo piped answers (non-TTY) so evidence/logs show the human decision.
        if not sys.stdin.isatty():
            print(text, flush=True)
        yes = bool(YES_RE.search(text))
        no = bool(NO_RE.search(text))
        if no:
            return False
        if yes:
            return True
        print("Please answer yes or no.", flush=True)
        print(prompt, end="", flush=True)
