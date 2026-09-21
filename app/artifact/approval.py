"""
Per-version draft → approved promotion for operators.

New versions start as draft (replay allowed, production --yes blocked).
After enough successful replays at a high enough rate they become approved.
"""

from __future__ import annotations

from typing import Any

APPROVAL_MIN_SUCCESSES = 3
APPROVAL_MIN_SUCCESS_RATE = 0.75
APPROVAL_DRAFT = "draft"
APPROVAL_APPROVED = "approved"


def compute_approval_status(*, successes: int, attempts: int) -> str:
    if successes >= APPROVAL_MIN_SUCCESSES and attempts > 0:
        if successes / attempts >= APPROVAL_MIN_SUCCESS_RATE:
            return APPROVAL_APPROVED
    return APPROVAL_DRAFT


def parse_int_map(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            out[str(int(key))] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def parse_approval_map(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            version_key = str(int(key))
        except (TypeError, ValueError):
            continue
        status = str(value or "").strip().lower()
        out[version_key] = (
            APPROVAL_APPROVED if status == APPROVAL_APPROVED else APPROVAL_DRAFT
        )
    return out


def normalize_version_maps(
    *,
    on_disk: list[int],
    usage_counts: dict[str, int],
    attempt_counts: dict[str, int],
    failure_counts: dict[str, int],
    approval: dict[str, str],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, str]]:
    usage = dict(usage_counts)
    attempts = dict(attempt_counts)
    failures = dict(failure_counts)
    status = dict(approval)

    # Bootstrap older metadata that only had usage_counts.
    for key, successes in list(usage.items()):
        attempts.setdefault(key, int(successes))
        failures.setdefault(
            key, max(0, int(attempts.get(key) or 0) - int(successes))
        )

    for version in on_disk:
        key = str(version)
        usage.setdefault(key, 0)
        attempts.setdefault(key, int(usage.get(key) or 0))
        failures.setdefault(
            key, max(0, int(attempts.get(key) or 0) - int(usage.get(key) or 0))
        )
        if key not in status:
            status[key] = compute_approval_status(
                successes=int(usage.get(key) or 0),
                attempts=int(attempts.get(key) or 0),
            )
    return usage, attempts, failures, status


def version_stats_from_meta(meta: dict[str, Any], version: int) -> dict[str, Any]:
    key = str(int(version))
    successes = int((meta.get("usage_counts") or {}).get(key) or 0)
    attempts = int((meta.get("attempt_counts") or {}).get(key) or 0)
    failures = int((meta.get("failure_counts") or {}).get(key) or 0)
    rate = (successes / attempts) if attempts else 0.0
    status = str((meta.get("approval") or {}).get(key) or APPROVAL_DRAFT)
    return {
        "version": int(version),
        "successes": successes,
        "attempts": attempts,
        "failures": failures,
        "success_rate": rate,
        "status": status,
        "approved": status == APPROVAL_APPROVED,
    }


def production_block_message(blocked: list[str]) -> str:
    return (
        "Production --yes requires approved operators. Still draft:\n  - "
        + "\n  - ".join(blocked)
        + f"\nNeed ≥{APPROVAL_MIN_SUCCESSES} successes at "
        f"≥{int(APPROVAL_MIN_SUCCESS_RATE * 100)}% success rate per version. "
        "Replay interactively (without --yes) until they promote."
    )
