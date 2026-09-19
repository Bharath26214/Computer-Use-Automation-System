from __future__ import annotations

import os
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

SESSION_KEY = "atlas-bank.session"


def default_profile_dir() -> Path:
    configured = (os.getenv("BROWSER_PROFILE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / ".atlas-browser"


class BrowserManager:
    """Shared Playwright session that keeps Atlas Bank localStorage across runs."""

    def __init__(self, headless: bool | None = None) -> None:
        if headless is None:
            headless = os.getenv("HEADLESS", "false").lower() in {"1", "true", "yes"}
        self.headless = headless
        self.profile_dir = default_profile_dir()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._session_cleared = False

    async def open(self) -> Page:
        if self.page is not None:
            return self.page

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        profile = str(self.profile_dir)
        launch_kwargs = {
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 900},
        }
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                profile,
                channel="chrome",
                **launch_kwargs,
            )
        except Exception:
            self._context = await self._playwright.chromium.launch_persistent_context(
                profile,
                **launch_kwargs,
            )
        self._browser = self._context.browser
        self.page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self.clear_login_session()
        return self.page

    async def clear_login_session(self) -> None:
        """Drop the signed-in session only; keep accounts, balances, and transfers."""
        if self._session_cleared:
            return
        page = self.page
        if page is None:
            return
        bank_url = os.getenv("BANK_URL", "http://127.0.0.1:5173/login").strip()
        origin = bank_url
        for suffix in ("/login", "/dashboard", "/transfer", "/transactions", "/register"):
            if origin.endswith(suffix):
                origin = origin[: -len(suffix)] or origin
                break
        origin = origin.rstrip("/") or "http://127.0.0.1:5173"
        try:
            await page.goto(origin + "/", wait_until="domcontentloaded")
            await page.evaluate(
                """(key) => { try { localStorage.removeItem(key); } catch (e) {} }""",
                SESSION_KEY,
            )
            self._session_cleared = True
        except Exception:
            # Bank may not be up yet; login steps will navigate later.
            pass

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        elif self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None
        self._session_cleared = False

    async def _first_match(self, candidates: list[Locator], selector: str) -> Locator:
        for locator in candidates:
            try:
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        raise ValueError(f"No matching element for: {selector}")

    async def locate(self, selector: str) -> Locator:
        page = await self.open()
        return await self._first_match(
            [
                page.get_by_test_id(selector),
                page.get_by_label(selector, exact=False),
                page.get_by_placeholder(selector, exact=False),
                page.get_by_role("textbox", name=selector, exact=False),
                page.get_by_role("button", name=selector, exact=False),
                page.get_by_role("link", name=selector, exact=False),
                page.get_by_text(selector, exact=False),
                page.locator(selector),
            ],
            selector,
        )

    async def locate_fillable(self, selector: str) -> Locator:
        page = await self.open()
        return await self._first_match(
            [
                page.get_by_label(selector, exact=False),
                page.get_by_placeholder(selector, exact=False),
                page.get_by_test_id(selector),
                page.get_by_role("textbox", name=selector, exact=False),
                page.locator(selector),
            ],
            selector,
        )

    async def locate_clickable(self, selector: str) -> Locator:
        page = await self.open()
        return await self._first_match(
            [
                page.get_by_role("button", name=selector, exact=False),
                page.get_by_role("link", name=selector, exact=False),
                page.get_by_test_id(selector),
                page.get_by_test_id(f"nav-{selector.lower().replace(' ', '-')}"),
                page.get_by_text(selector, exact=True),
                page.locator(selector),
            ],
            selector,
        )
