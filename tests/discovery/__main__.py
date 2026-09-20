"""
Discovery test CLI.

Forces discovery only for the case capability
(ATLAS_FORCE_DISCOVERY_ARTIFACT). Nested operators (lookup/transfer inside
delete) replay when already saved. New operator versions are created only when
steps or handled-error sets differ (e.g. reload / page_not_found users).

Examples:
  python3 -m tests.discovery list
  python3 -m tests.discovery test1
  python3 -m tests.discovery test1 --print-only
  python3 -m tests.discovery all
"""

from __future__ import annotations

import argparse
import os
import sys

from tests import cli_command, print_case, run_cli
from tests.discovery.cases import CASES, get_case


def _run_case(test_id: str, *, print_only: bool, auto_yes: bool = False) -> int:
    case = get_case(test_id)
    print_case(case)
    if print_only:
        return 0

    # Discovery harness: force discovery only for this case's capability.
    # Nested operators (e.g. lookup inside delete) may still replay.
    os.environ.pop("ATLAS_FORCE_REPLAY", None)
    os.environ["ATLAS_FORCE_DISCOVERY"] = "1"
    os.environ["ATLAS_FORCE_DISCOVERY_ARTIFACT"] = str(case["artifact_id"])

    viewport = case.get("viewport", "desktop")
    confirm = case.get("confirm_reply")
    if auto_yes and not (confirm and str(confirm).strip().lower() in {"no", "n"}):
        confirm = "yes"

    if case.get("prep_query"):
        prep = cli_command(
            username=case["username"],
            query=case["prep_query"],
            viewport=viewport,
            auto_confirm=confirm,
        )
        code = run_cli(prep)
        if code != 0:
            print(f"[prep failed] exit={code} for {case['id']}")
            return code

    command = cli_command(
        username=case["username"],
        query=case["query"],
        viewport=viewport,
        auto_confirm=confirm,
    )
    code = run_cli(command)
    expect = case.get("expect", "pass")
    if expect == "fail":
        if code == 0:
            print(f"[warn] {case['id']} expected fail/hard_failure but exited 0")
        else:
            print(f"[ok] {case['id']} failed as expected for hard_failure")
        return 0
    if code != 0:
        print(f"[fail] {case['id']} exit={code}")
    else:
        print(f"[ok] {case['id']}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Atlas Bank discovery test cases (default viewport: desktop). "
            "Forces discovery and appends new operator versions without deleting older ones."
        ),
    )
    parser.add_argument(
        "target",
        help="test1..test13, list, or all",
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
        help="Auto-answer HITL prompts with yes for every case (except explicit reject cases).",
    )
    args = parser.parse_args(argv)
    target = args.target.strip().lower()

    if target == "list":
        for case in CASES:
            print_case(case)
            print()
        print(f"Total: {len(CASES)} discovery cases")
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
