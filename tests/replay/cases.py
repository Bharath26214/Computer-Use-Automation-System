"""
16 replay test cases — run AFTER discovery, never fall back to discovery.

No prep runs. Each case is a single CLI invocation.

HITL methodology (same as discovery — see tests.hitl):
  Agent clicks → app confirmation page → human Yes/Confirm in browser → resume
  (or confirm_reply=yes / --yes to auto-click app confirms).

Group A — first 4 from discovery (alex123):
  lookup → transfer <5k → delete savings → open savings

Group B — edge subcases (alex123):
  open already exists
  transfer > $5000 (HITL accept)
  transfer > $5000 (HITL reject)
  transfer insufficient funds

Group C — unique viewport cases:
  test9–10  tablet: lookup, transfer
  test11–12 mobile: delete savings, open savings

Group D — error-handling replay (scenario users):
  test13–14 casey404 page_not_found: lookup, transfer
  test15–16 taylor321 reloading: lookup, transfer

Run:
  python3 -m tests.replay list
  python3 -m tests.replay test1
  python3 -m tests.replay all --yes
"""

from __future__ import annotations

from typing import Any

from tests import DEFAULT_VIEWPORT
from tests.discovery.cases import (
    DELETE_QUERY,
    LOOKUP_QUERY,
    OPEN_QUERY,
    TRANSFER_QUERY,
)
from tests.hitl import UNSET, hitl_defaults

USER = "alex123"
SCENARIO = "normal"


def _case(
    test_id: str,
    *,
    title: str,
    artifact_id: str,
    query: str,
    username: str = USER,
    scenario: str = SCENARIO,
    viewport: str = DEFAULT_VIEWPORT,
    expect: str = "pass",
    expect_outcome: str | None = None,
    confirm_reply: Any = UNSET,
    notes: str | None = None,
    needs_hitl: bool | None = None,
) -> dict[str, Any]:
    hitl = hitl_defaults(
        artifact_id,
        query=query,
        expect=expect,
        confirm_reply=confirm_reply,
        notes=notes,
        needs_hitl=needs_hitl,
    )
    case: dict[str, Any] = {
        "id": test_id,
        "title": title,
        "mode": "replay",
        "username": username,
        "scenario": scenario,
        "artifact_id": artifact_id,
        "query": query,
        "viewport": viewport,
        "expect": expect,
        "expect_outcome": expect_outcome,
        "clear_operator": False,
    }
    case.update(hitl)
    return case


# test1–4: identical to discovery test1–4 (alex123).
DISCOVERY_MIRROR: list[dict[str, Any]] = [
    _case(
        "test1",
        title="lookup_balance (normal)",
        artifact_id="lookup_balance",
        query=LOOKUP_QUERY,
        expect_outcome="Balance retrieved",
        notes="Identical to discovery test1. No HITL.",
    ),
    _case(
        "test2",
        title="transfer_funds under $5000 (normal)",
        artifact_id="transfer_funds",
        query=TRANSFER_QUERY,
        expect_outcome="Transfer completed",
        notes="Identical to discovery test2. Under $5000 — no HITL.",
    ),
    _case(
        "test3",
        title="delete_account savings (normal)",
        artifact_id="delete_account",
        query=DELETE_QUERY,
        expect_outcome="Account deleted",
        notes="Identical to discovery test3. " + hitl_defaults("delete_account")["notes"],
    ),
    _case(
        "test4",
        title="open_account savings (normal)",
        artifact_id="open_account",
        query=OPEN_QUERY,
        expect_outcome="Account opened",
        notes="Identical to discovery test4. " + hitl_defaults("open_account")["notes"],
    ),
]


EDGE_CASES: list[dict[str, Any]] = [
    _case(
        "test5",
        title="open_account — account already exists",
        artifact_id="open_account",
        query="Open a checking account named Extra Checking for personal use",
        expect_outcome="Account already exists",
        confirm_reply=None,
        needs_hitl=False,
        notes="Seeded checking already open — no Open click / no HITL.",
    ),
    _case(
        "test6",
        title="transfer_funds — amount over $5000 (HITL accept)",
        artifact_id="transfer_funds",
        query="Transfer 6000 from checking to savings",
        expect_outcome="Transfer completed",
        confirm_reply="yes",
    ),
    _case(
        "test7",
        title="transfer_funds — amount over $5000 (HITL reject)",
        artifact_id="transfer_funds",
        query="Transfer 6000 from checking to savings",
        expect="fail",
        expect_outcome="Human did not confirm",
        confirm_reply="no",
    ),
    _case(
        "test8",
        title="transfer_funds — insufficient funds",
        artifact_id="transfer_funds",
        query="Transfer 99999 from checking to savings",
        expect_outcome="Insufficient funds",
        confirm_reply=None,
        needs_hitl=False,
        notes="Amount exceeds balance — blocked before Confirm; no HITL.",
    ),
]


VIEWPORT_CASES: list[dict[str, Any]] = [
    _case(
        "test9",
        title="lookup_balance — account exists (tablet)",
        artifact_id="lookup_balance",
        query=LOOKUP_QUERY,
        viewport="tablet",
        expect_outcome="Balance retrieved",
        notes="Tablet lookup. No HITL.",
    ),
    _case(
        "test10",
        title="transfer_funds — under $5000 (tablet)",
        artifact_id="transfer_funds",
        query=TRANSFER_QUERY,
        viewport="tablet",
        expect_outcome="Transfer completed",
        notes="Tablet transfer under $5000 — no HITL.",
    ),
    _case(
        "test11",
        title="delete_account — account exists (mobile)",
        artifact_id="delete_account",
        query=DELETE_QUERY,
        viewport="mobile",
        expect_outcome="Account deleted",
    ),
    _case(
        "test12",
        title="open_account — account does not exist (mobile)",
        artifact_id="open_account",
        query=OPEN_QUERY,
        viewport="mobile",
        expect_outcome="Account opened",
        notes="Follows mobile delete (savings missing). "
        + hitl_defaults("open_account")["notes"],
    ),
]


ERROR_CASES: list[dict[str, Any]] = [
    _case(
        "test13",
        title="lookup_balance (page_not_found)",
        username="casey404",
        scenario="page_not_found",
        artifact_id="lookup_balance",
        query=LOOKUP_QUERY,
        expect_outcome="Balance retrieved",
        notes="Replays page_not_found operator. No HITL.",
    ),
    _case(
        "test14",
        title="transfer_funds under $5000 (page_not_found)",
        username="casey404",
        scenario="page_not_found",
        artifact_id="transfer_funds",
        query=TRANSFER_QUERY,
        expect_outcome="Transfer completed",
        notes="Replays page_not_found operator. Under $5000 — no HITL.",
    ),
    _case(
        "test15",
        title="lookup_balance (reloading)",
        username="taylor321",
        scenario="reloading",
        artifact_id="lookup_balance",
        query=LOOKUP_QUERY,
        expect_outcome="Balance retrieved",
        notes="Replays reloading operator. No HITL.",
    ),
    _case(
        "test16",
        title="transfer_funds under $5000 (reloading)",
        username="taylor321",
        scenario="reloading",
        artifact_id="transfer_funds",
        query=TRANSFER_QUERY,
        expect_outcome="Transfer completed",
        notes="Replays reloading operator. Under $5000 — no HITL.",
    ),
]


CASES: list[dict[str, Any]] = [
    *DISCOVERY_MIRROR,
    *EDGE_CASES,
    *VIEWPORT_CASES,
    *ERROR_CASES,
]

CASES_BY_ID = {case["id"]: case for case in CASES}


def get_case(test_id: str) -> dict[str, Any]:
    key = test_id.strip().lower()
    if key not in CASES_BY_ID:
        known = ", ".join(CASES_BY_ID)
        raise KeyError(f"Unknown replay test {test_id!r}. Expected one of: {known}")
    return CASES_BY_ID[key]
