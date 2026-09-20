from __future__ import annotations

import os
from typing import Any

# Named device profiles for cross-screen replay. Playwright always drives the
# page via DOM locators (testid / role / label); never click coordinates.
VIEWPORT_PROFILES: dict[str, dict[str, int]] = {
    "desktop": {"width": 1280, "height": 900},
    "laptop": {"width": 1366, "height": 768},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 390, "height": 844},
}

DEFAULT_PROFILE = "desktop"


def resolve_viewport(
    profile: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """
    Resolve the active viewport from explicit args or env.

    Env (any of):
      VIEWPORT / DEVICE_PROFILE  → desktop|laptop|tablet|mobile
      VIEWPORT_WIDTH / VIEWPORT_HEIGHT → exact pixels (profile becomes "custom")
    """
    env_profile = (
        profile
        or os.getenv("VIEWPORT")
        or os.getenv("DEVICE_PROFILE")
        or ""
    ).strip().lower()
    env_w = width if width is not None else _env_int("VIEWPORT_WIDTH")
    env_h = height if height is not None else _env_int("VIEWPORT_HEIGHT")

    if env_w and env_h:
        matched = _match_profile(env_w, env_h)
        return {
            "profile": matched or "custom",
            "width": int(env_w),
            "height": int(env_h),
            "locator_policy": "dom_only",
        }

    name = env_profile if env_profile in VIEWPORT_PROFILES else DEFAULT_PROFILE
    size = VIEWPORT_PROFILES[name]
    return {
        "profile": name,
        "width": size["width"],
        "height": size["height"],
        "locator_policy": "dom_only",
    }


def current_viewport() -> dict[str, Any]:
    return resolve_viewport()


def _env_int(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _match_profile(width: int, height: int) -> str | None:
    for name, size in VIEWPORT_PROFILES.items():
        if size["width"] == width and size["height"] == height:
            return name
    return None


def viewport_compatible(artifact: dict[str, Any] | None, active: dict[str, Any] | None = None) -> bool:
    """DOM-only artifacts are portable; coordinate-based ones are not."""
    del active
    if not artifact:
        return False
    policy = str(artifact.get("locator_policy") or "dom_only").lower()
    return policy in {"dom", "dom_only", ""}


def viewport_preference_score(artifact: dict[str, Any], active: dict[str, Any] | None = None) -> int:
    """Higher = better match for trying replay first on this device."""
    active = active or current_viewport()
    score = 0
    policy = str(artifact.get("locator_policy") or "dom_only").lower()
    if policy in {"dom", "dom_only", ""}:
        score += 10
    validated = [str(item) for item in (artifact.get("viewports_validated") or [])]
    profile = str(active.get("profile") or "")
    if not validated:
        score += 2  # untagged = assumed portable
    elif profile in validated or "any" in validated:
        score += 5
    recorded = (artifact.get("viewport") or {}).get("profile")
    if recorded and recorded == profile:
        score += 3
    return score
