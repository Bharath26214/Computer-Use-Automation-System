"""
Replay test CLI.

Sets ATLAS_FORCE_REPLAY=1 so runners never fall back to discovery.
No prep runs — each case is a single CLI invocation.

HITL (see tests.hitl): agent clicks → app confirm page → YOU click Yes/Confirm
→ resume. Only test6/test7 bake confirm_reply; other HITL cases are interactive
unless you pass `--yes`. Unattended: `all --yes` (test7 stays --no).

Examples:
  python3 -m tests.replay list
  python3 -m tests.replay test3
  python3 -m tests.replay all --yes
"""

from __future__ import annotations

import argparse
import os
import sys

from tests import cli_command, print_case, run_cli
from tests.replay.cases import CASES, get_case


def _arm_replay_mode() -> None:
    os.environ.pop("ATLAS_FORCE_DISCOVERY", None)
    os.environ.pop("ATLAS_FORCE_DISCOVERY_ARTIFACT", None)
    os.environ["ATLAS_FORCE_REPLAY"] = "1"


def _resolve_confirm(case: dict, *, auto_yes: bool) -> str | None:
    reply = case.get("confirm_reply")
    # Keep explicit reject cases (e.g. HITL no) even when --yes is set.
    if reply and str(reply).strip().lower() in {"no", "n"}:
        return "no"
    if auto_yes:
        return "yes"
    return reply


def _run_case(test_id: str, *, print_only: bool, auto_yes: bool = False) -> int:
    case = get_case(test_id)
    print_case(case)
    if print_only:
        return 0

    _arm_replay_mode()
    viewport = case.get("viewport", "desktop")
    confirm = _resolve_confirm(case, auto_yes=auto_yes)

    command = cli_command(
        username=case["username"],
        query=case["query"],
        viewport=viewport,
        auto_confirm=confirm,
    )
    # Prefer CLI --yes/--no; only pipe stdin for multi-line confirm sequences.
    reply = case.get("confirm_reply")
    stdin_text = None
    if reply and "\n" in str(reply).strip() and not auto_yes:
        stdin_text = f"{reply}\n" if not str(reply).endswith("\n") else str(reply)
    code = run_cli(command, stdin_text=stdin_text)
    expect = case.get("expect", "pass")
    if expect == "fail":
        if code == 0:
            print(f"[warn] {case['id']} expected fail but exited 0")
        else:
            print(f"[ok] {case['id']} failed as expected")
        return 0
    if code != 0:
        print(f"[fail] {case['id']} exit={code}")
    else:
        outcome = case.get("expect_outcome")
        if outcome:
            print(f"[ok] {case['id']} (expect outcome: {outcome})")
        else:
            print(f"[ok] {case['id']}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Atlas Bank replay test cases "
            "(4 discovery + 4 edge + 2 tablet + 2 mobile + 4 error). "
            "Never discovers; no account prep."
        ),
    )
    parser.add_argument(
        "target",
        help="test1..test16, list, or all",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the CLI command without executing.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Auto-confirm HITL handoffs with --yes on every case (except explicit reject cases).",
    )
    args = parser.parse_args(argv)
    target = args.target.strip().lower()

    if target == "list":
        for case in CASES:
            print_case(case)
            print()
        print(f"Total: {len(CASES)} replay cases")
        return 0

    if target == "all":
        failed = 0
        for case in CASES:
            print("=" * 72)
            code = _run_case(
                case["id"],
                print_only=args.print_only,
                auto_yes=args.yes,
            )
            if code != 0:
                failed += 1
        print("=" * 72)
        print(f"Done. failures={failed}/{len(CASES)}")
        return 1 if failed else 0

    try:
        return _run_case(target, print_only=args.print_only, auto_yes=args.yes)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
