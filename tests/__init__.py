"""Shared helpers for discovery/replay CLI test harnesses."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPERATORS_DIR = ROOT / "operators"
DEFAULT_VIEWPORT = "desktop"


def cli_command(
    *,
    username: str,
    query: str,
    viewport: str = DEFAULT_VIEWPORT,
    auto_confirm: str | None = None,
) -> str:
    """Exact shell command for a case (default desktop viewport).

    Dollar signs are escaped so amounts like $100 are not expanded by the shell
    ($100 → ${1}00 → 00).
    auto_confirm: "yes" → --yes, "no" → --no.
    """
    q = (
        query.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    flags = f"--viewport {viewport} -u {username}"
    reply = (auto_confirm or "").strip().lower()
    if reply in {"yes", "y", "1", "true"}:
        flags += " --yes"
    elif reply in {"no", "n", "0", "false"}:
        flags += " --no"
    return f'python3 -m app.main {flags} "{q}"'


def run_cli(
    command: str,
    *,
    cwd: Path | None = None,
    stdin_text: str | None = None,
) -> int:
    print(f"$ {command}")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Test harness may --yes against draft operators while accumulating approval stats.
    env.setdefault("ATLAS_ALLOW_DRAFT_YES", "1")
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd or ROOT),
        env=env,
        input=stdin_text,
        text=True if stdin_text is not None else None,
    )
    return int(completed.returncode)


def print_case(case: dict[str, Any]) -> None:
    print(f"[{case['id']}] {case['title']}")
    print(f"  mode:       {case.get('mode', 'discovery')}")
    print(f"  user:       {case['username']} ({case['scenario']})")
    print(f"  capability: {case['artifact_id']}")
    print(f"  viewport:   {case.get('viewport', DEFAULT_VIEWPORT)}")
    print(f"  expect:     {case.get('expect', 'pass')}")
    if case.get("expect_outcome"):
        print(f"  outcome:    {case['expect_outcome']}")
    if case.get("confirm_reply"):
        reply = str(case["confirm_reply"]).strip().lower()
        if reply in {"yes", "y"}:
            print("  confirm:    yes (CLI --yes → agent auto-clicks app confirms)")
        elif reply in {"no", "n"}:
            print("  confirm:    no (CLI --no → abort app confirmation handoff)")
        else:
            print(f"  confirm:    {case['confirm_reply']}")
    elif case.get("artifact_id") in {"delete_account", "open_account"} or (
        "over $5000" in str(case.get("title") or "").lower()
        and "reject" not in str(case.get("title") or "").lower()
    ):
        print("  confirm:    interactive (click app Yes/Confirm, then type resume)")
        print("              add harness --yes to auto-click instead")
    if case.get("accounts"):
        print(f"  accounts:   {case['accounts']}")
    if case.get("notes"):
        print(f"  notes:      {case['notes']}")
    if case.get("prep_query"):
        print(
            "  prep:       "
            + cli_command(
                username=case["username"],
                query=case["prep_query"],
                viewport=case.get("viewport", DEFAULT_VIEWPORT),
            )
        )
    print(
        "  cli:        "
        + cli_command(
            username=case["username"],
            query=case["query"],
            viewport=case.get("viewport", DEFAULT_VIEWPORT),
            auto_confirm=case.get("confirm_reply"),
        )
    )
