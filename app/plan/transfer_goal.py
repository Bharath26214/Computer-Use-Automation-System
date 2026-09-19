from __future__ import annotations

import re

FROM_TO_RE = re.compile(r"from\s+(savings|checking)\s+to\s+(savings|checking)")
TO_FROM_RE = re.compile(r"to\s+(savings|checking)\s+from\s+(savings|checking)")
AMOUNT_PATTERNS = [
    re.compile(
        r"(?:transfer|move|send)\s+(?:me\s+)?\$?\s*([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    ),
    re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)"),
    re.compile(r"\b([\d,]+(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b", re.IGNORECASE),
    re.compile(r"\b([\d,]+(?:\.\d{1,2})?)\s+from\s+(?:savings|checking)\b", re.IGNORECASE),
]


def is_transfer_goal(goal: str) -> bool:
    text = (goal or "").lower()
    if any(token in text for token in ("transfer", "send money", "move money", "wire")):
        return True
    if re.search(r"(savings|checking).*(?:to|->).*(savings|checking)", text):
        return True
    return False


def extract_amount(goal: str) -> str | None:
    text = goal or ""
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).replace(",", "")
    return None


def parse_transfer_goal(goal: str) -> dict[str, str]:
    text = (goal or "").lower()
    amount = extract_amount(goal) or ""

    from_account = "Savings"
    to_account = "Checking"
    from_to = FROM_TO_RE.search(text)
    to_from = TO_FROM_RE.search(text)
    if from_to:
        from_account = from_to.group(1).title()
        to_account = from_to.group(2).title()
    elif to_from:
        to_account = to_from.group(1).title()
        from_account = to_from.group(2).title()
    elif re.search(r"checking.+(?:to|->).+savings", text):
        from_account, to_account = "Checking", "Savings"
    elif re.search(r"savings.+(?:to|->).+checking", text):
        from_account, to_account = "Savings", "Checking"

    memo_match = re.search(r"memo(?:[:\s]+)(.+)$", goal or "", re.IGNORECASE)
    memo = memo_match.group(1).strip() if memo_match else ""
    return {
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
        "memo": memo,
    }


def transfer_artifact_id(goal: str) -> str:
    return "transfer_funds"
