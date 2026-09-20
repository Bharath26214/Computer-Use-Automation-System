"""
13 discovery test cases (default viewport: desktop).

Sequence per scenario user (both accounts seeded):
  1. lookup_balance
  2. transfer_funds (< $5000)
  3. delete_account (savings)
  4. open_account (re-create savings)

  4 normal (alex123)
  4 page_not_found (casey404)
  4 reloading (taylor321)
  1 hard_failure lookup (blake000)

Run:
  python3 -m tests.discovery list
  python3 -m tests.discovery test1
  python3 -m tests.discovery all
"""

from __future__ import annotations

from typing import Any

from tests import DEFAULT_VIEWPORT

LOOKUP_QUERY = "What is my checking account balance?"
TRANSFER_QUERY = "Transfer 100 from checking to savings"
DELETE_QUERY = "Delete my savings account"
OPEN_QUERY = "Open a savings account named Travel Fund for personal use"


def _case(
    test_id: str,
    *,
    title: str,
    username: str,
    scenario: str,
    artifact_id: str,
    query: str,
    expect: str = "pass",
) -> dict[str, Any]:
    return {
        "id": test_id,
        "title": title,
        "mode": "discovery",
        "username": username,
        "scenario": scenario,
        "artifact_id": artifact_id,
        "query": query,
        "viewport": DEFAULT_VIEWPORT,
        "expect": expect,
        "clear_operator": False,
    }


def _block(
    *,
    start: int,
    username: str,
    scenario: str,
) -> list[dict[str, Any]]:
    """lookup → transfer → delete savings → create savings."""
    return [
        _case(
            f"test{start}",
            title=f"lookup_balance ({scenario})",
            username=username,
            scenario=scenario,
            artifact_id="lookup_balance",
            query=LOOKUP_QUERY,
        ),
        _case(
            f"test{start + 1}",
            title=f"transfer_funds under $5000 ({scenario})",
            username=username,
            scenario=scenario,
            artifact_id="transfer_funds",
            query=TRANSFER_QUERY,
        ),
        _case(
            f"test{start + 2}",
            title=f"delete_account savings ({scenario})",
            username=username,
            scenario=scenario,
            artifact_id="delete_account",
            query=DELETE_QUERY,
        ),
        _case(
            f"test{start + 3}",
            title=f"open_account savings ({scenario})",
            username=username,
            scenario=scenario,
            artifact_id="open_account",
            query=OPEN_QUERY,
        ),
    ]


CASES: list[dict[str, Any]] = [
    *_block(start=1, username="alex123", scenario="normal"),
    *_block(start=5, username="casey404", scenario="page_not_found"),
    *_block(start=9, username="taylor321", scenario="reloading"),
    _case(
        "test13",
        title="lookup_balance (hard_failure)",
        username="blake000",
        scenario="hard_failure",
        artifact_id="lookup_balance",
        query=LOOKUP_QUERY,
        expect="fail",
    ),
]

CASES_BY_ID = {case["id"]: case for case in CASES}


def get_case(test_id: str) -> dict[str, Any]:
    key = test_id.strip().lower()
    if key not in CASES_BY_ID:
        known = ", ".join(CASES_BY_ID)
        raise KeyError(f"Unknown discovery test {test_id!r}. Expected one of: {known}")
    return CASES_BY_ID[key]
