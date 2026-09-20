from __future__ import annotations

import re
import select
import sys
import time

YES_RE = re.compile(r"\b(y|yes|yeah|yep|sure|ok|okay|confirm)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(n|no|nope|cancel|stop|abort|never)\b", re.IGNORECASE)

# Human confirmation must answer within this window or the run fails.
CONFIRM_TIMEOUT_SEC = 15.0


class ConfirmationTimeout(Exception):
    """Raised when the operator does not answer yes/no in time."""


def ask_yes_no(prompt: str, timeout_sec: float = CONFIRM_TIMEOUT_SEC) -> bool:
    """
    Ask for yes/no with a hard timeout.

    Returns True on yes, False on no.
    Raises ConfirmationTimeout if no answer within timeout_sec.
    """
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
        yes = bool(YES_RE.search(text))
        no = bool(NO_RE.search(text))
        if no:
            return False
        if yes:
            return True
        print("Please answer yes or no.", flush=True)
        print(prompt, end="", flush=True)
