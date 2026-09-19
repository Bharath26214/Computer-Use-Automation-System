from __future__ import annotations

import re

YES_RE = re.compile(r"\b(y|yes|yeah|yep|sure|ok|okay|confirm)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(n|no|nope|cancel|stop|abort|never)\b", re.IGNORECASE)


def ask_yes_no(prompt: str) -> bool:
    while True:
        try:
            reply = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not reply:
            return False
        yes = bool(YES_RE.search(reply))
        no = bool(NO_RE.search(reply))
        if no:
            return False
        if yes:
            return True
        print("Please answer yes or no.")
