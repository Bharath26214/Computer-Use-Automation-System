from __future__ import annotations

import os
import re
import select
import sys
import time

YES_RE = re.compile(r"\b(y|yes|yeah|yep|sure|ok|okay|confirm)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(n|no|nope|cancel|stop|abort|never)\b", re.IGNORECASE)
RESUME_RE = re.compile(r"^\s*(resume|r|continue|go)\s*$", re.IGNORECASE)
ABORT_RE = re.compile(r"^\s*(abort|cancel|stop|quit|no|n)\s*$", re.IGNORECASE)

# Human confirmation must answer within this window or the run fails.
CONFIRM_TIMEOUT_SEC = 60.0

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


def confirmation_label(target: str | None) -> str:
    """Friendly label for app confirmation controls."""
    text = str(target or "").strip()
    lower = text.lower()
    if "transfer-before-delete" in lower or "transfer funds before" in lower:
        return "Yes"
    if lower == "yes":
        return "Yes"
    if "confirm transfer" in lower:
        return "Confirm Transfer"
    if lower.startswith("confirm-delete") or (
        "delete" in lower and "confirm" in lower and "transfer" not in lower
    ):
        return "Yes, Confirm"
    if lower.startswith("confirm-open") or ("open" in lower and "confirm" in lower):
        return "Yes, Confirm"
    if "yes" in lower and "confirm" in lower:
        return "Yes, Confirm"
    return text or "Yes, Confirm"


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


def ask_browser_handoff(button_label: str) -> bool:
    """
    Pause so the human can click the app confirmation control in the browser.

    Flow: agent already opened the confirmation page → human clicks Yes, Confirm
    (or Confirm Transfer) in the app → type resume. Type abort to cancel.

    With --yes / ATLAS_AUTO_CONFIRM=yes: return True so the agent clicks instead.
    With --no: return False (abort).
    """
    label = confirmation_label(button_label)
    auto = auto_confirm_reply()
    if auto is True:
        print("", flush=True)
        print("=" * 64, flush=True)
        print("HANDOFF — automation will click for you", flush=True)
        print("=" * 64, flush=True)
        print(f"Action: click “{label}” on the confirmation page", flush=True)
        print("(auto-yes) agent clicks", flush=True)
        print("=" * 64, flush=True)
        return True
    if auto is False:
        print("", flush=True)
        print("=" * 64, flush=True)
        print("HANDOFF — cancelled", flush=True)
        print("=" * 64, flush=True)
        print(f"Action: click “{label}” on the confirmation page", flush=True)
        print("(auto-no) abort", flush=True)
        print("=" * 64, flush=True)
        return False

    print("", flush=True)
    print("=" * 64, flush=True)
    print("CONFIRMATION PAGE — your turn in the browser", flush=True)
    print("=" * 64, flush=True)
    print(f"Click “{label}” on the app confirmation page.", flush=True)
    print("Then type resume here. Type abort to cancel.", flush=True)
    print("=" * 64, flush=True)

    timeout_sec = CONFIRM_TIMEOUT_SEC
    print(f"resume> (answer within {int(timeout_sec)}s) ", end="", flush=True)
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
        if not sys.stdin.isatty():
            print(text, flush=True)
        if ABORT_RE.match(text):
            return False
        if RESUME_RE.match(text):
            return True
        print("Type resume after you click in the browser, or abort to cancel.", flush=True)
        print("resume> ", end="", flush=True)
