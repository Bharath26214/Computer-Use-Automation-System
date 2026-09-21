"""
Shared HITL methodology for discovery and replay tests.

App confirmation flow (not CLI yes/no before the agent click):

1. Agent clicks the initiating control in the bank UI
   - Delete … Account
   - Open … Account
   - Review Transfer (large transfers reach Confirm Transfer next)

2. App shows a confirmation page:
   - Delete with balance → “Transfer funds before delete?” → Yes / No
   - Delete with zero balance / Open → “Yes, Confirm”
   - Transfer > $5000 → “Confirm Transfer” on Transfer Review

3. Human clicks that button in the browser, then types `resume` in the CLI
   (or `abort` to cancel).

4. Delete with nonzero balance needs two handoffs:
   Yes (transfer) + resume → agent transfers → Delete again →
   Yes, Confirm + resume.

Automated runs use confirm_reply="yes" / CLI --yes so the agent clicks the
app confirm controls. confirm_reply="no" / --no aborts the handoff.
"""

from __future__ import annotations

from typing import Any

# Artifacts that open an app confirmation page (HITL).
HITL_ARTIFACTS = frozenset({"delete_account", "open_account", "transfer_funds"})

# Sentinel: caller did not pass confirm_reply (apply defaults).
UNSET = object()
_UNSET = UNSET  # backward-compatible alias

DELETE_HITL_NOTES = (
    "HITL: agent clicks Delete → app Transfer Yes/No if balance > 0 "
    "(you click Yes, then resume) → transfer → Delete again → "
    "you click Yes, Confirm, then resume. "
    "Zero balance: one Yes, Confirm + resume. "
    "Pass harness --yes only if you want the agent to click confirms for you."
)

OPEN_HITL_NOTES = (
    "HITL: agent clicks Open … Account → you click Yes, Confirm in the app, "
    "then type resume. Pass harness --yes to auto-click instead."
)

TRANSFER_SMALL_NOTES = (
    "Under $5000: no HITL — agent clicks Confirm Transfer."
)

TRANSFER_LARGE_ACCEPT_NOTES = (
    "HITL: after Review Transfer, click Confirm Transfer in the app, "
    "then resume. Case uses confirm_reply=yes / --yes for unattended accept."
)

TRANSFER_LARGE_REJECT_NOTES = (
    "HITL reject: --no / abort so Confirm Transfer is not completed."
)


def hitl_defaults(
    artifact_id: str,
    *,
    query: str = "",
    expect: str = "pass",
    confirm_reply: Any = _UNSET,
    notes: str | None = None,
    needs_hitl: bool | None = None,
) -> dict[str, Any]:
    """
    Default notes (and optional confirm_reply) for app-confirmation HITL cases.

    Do NOT auto-set confirm_reply=yes for delete/open — that would add CLI --yes
    and the agent would click Yes/Confirm without the human. Interactive runs
    wait for browser click + resume. Pass harness `--yes` (or explicit
    confirm_reply) for unattended auto-click.
    """
    out: dict[str, Any] = {}
    aid = (artifact_id or "").strip().lower()
    q = (query or "").lower()
    large_transfer = aid == "transfer_funds" and _looks_large_transfer(q)
    use_hitl = needs_hitl
    if use_hitl is None:
        use_hitl = aid in {"delete_account", "open_account"} or large_transfer

    if confirm_reply is not _UNSET:
        if confirm_reply is not None:
            out["confirm_reply"] = confirm_reply
    elif use_hitl and expect == "fail" and large_transfer:
        # Reject cases always need --no so they don't hang waiting for resume.
        out["confirm_reply"] = "no"
    # Intentionally no default confirm_reply=yes for delete/open/large-accept.
    # Use: python3 -m tests.discovery test3 --yes   OR   all --yes

    if notes is not None:
        out["notes"] = notes
    elif not use_hitl:
        if aid == "transfer_funds":
            out["notes"] = TRANSFER_SMALL_NOTES
    elif aid == "delete_account":
        out["notes"] = DELETE_HITL_NOTES
    elif aid == "open_account":
        out["notes"] = OPEN_HITL_NOTES
    elif aid == "transfer_funds":
        if large_transfer and expect == "fail":
            out["notes"] = TRANSFER_LARGE_REJECT_NOTES
        elif large_transfer:
            out["notes"] = TRANSFER_LARGE_ACCEPT_NOTES
        else:
            out["notes"] = TRANSFER_SMALL_NOTES

    return out


def _looks_large_transfer(query: str) -> bool:
    """True when the query amount is clearly over $5000."""
    import re

    match = re.search(r"(?:transfer|send)\s+\$?\s*([\d,]+(?:\.\d+)?)", query, re.I)
    if not match:
        match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", query)
    if not match:
        return False
    try:
        return float(match.group(1).replace(",", "")) > 5000
    except ValueError:
        return False
