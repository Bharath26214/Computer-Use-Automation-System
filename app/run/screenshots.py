"""Playwright screenshot helpers for evidence run folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.run.logger import RunLogger


async def capture_run_screenshot(
    run_logger: RunLogger | None,
    page: Any,
    name: str,
) -> Path | None:
    """Save a named screenshot under the active run directory, if a logger exists."""
    if run_logger is None or page is None:
        return None
    return await run_logger.capture_screenshot(page, name)
