from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import Browser as PlaywrightBrowser
from playwright.sync_api import BrowserContext, Locator, Page, Playwright, sync_playwright

from app.browser.viewport import current_viewport

SESSION_KEY = "atlas-bank.session"


def default_profile_dir() -> Path:
    configured = (os.getenv("BROWSER_PROFILE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / ".atlas-browser"


class Browser:
    """Playwright browser with navigate, fill, click, and read."""

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.profile_dir = default_profile_dir()
        self.viewport = current_viewport()
        self._playwright: Playwright | None = None
        self._browser: PlaywrightBrowser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._session_cleared = False

    def open(self) -> None:
        if self._page is not None:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        profile = str(self.profile_dir)
        size = {
            "width": int(self.viewport.get("width") or 1280),
            "height": int(self.viewport.get("height") or 900),
        }
        launch_kwargs = {
            "headless": self.headless,
            "viewport": size,
        }
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                profile,
                channel="chrome",
                **launch_kwargs,
            )
        except Exception:
            self._context = self._playwright.chromium.launch_persistent_context(
                profile,
                **launch_kwargs,
            )
        self._browser = self._context.browser
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_viewport_size(size)
        self.clear_login_session()

    def clear_login_session(self) -> None:
        if self._session_cleared or self._page is None:
            return
        bank_url = os.getenv("BANK_URL", "http://localhost:5173/login").strip()
        origin = bank_url
        for suffix in ("/login", "/dashboard", "/transfer", "/transactions", "/register"):
            if origin.endswith(suffix):
                origin = origin[: -len(suffix)] or origin
                break
        origin = origin.rstrip("/") or "http://localhost:5173"
        try:
            self._page.goto(origin + "/", wait_until="domcontentloaded")
            self._page.evaluate(
                """(key) => { try { localStorage.removeItem(key); } catch (e) {} }""",
                SESSION_KEY,
            )
            self._session_cleared = True
        except Exception:
            pass

    def navigate(self, url: str) -> str:
        page = self._ensure_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        return page.url

    def fill(self, selector: str, value: str) -> None:
        self._locate_fillable(selector).fill(value)

    def click(self, selector: str) -> None:
        self._locate_clickable(selector).click()
        self._ensure_page().wait_for_load_state("networkidle")

    def read(self, selector: str | None = None) -> str:
        page = self._ensure_page()
        if selector:
            return self._locate(selector).inner_text()
        return f"URL: {page.url}\nTitle: {page.title()}\n\n{page.inner_text('body')}"

    def wait_for(self, selector: str, timeout: int = 15000) -> None:
        page = self._ensure_page()
        try:
            page.get_by_test_id(selector).wait_for(state="visible", timeout=timeout)
            return
        except Exception:
            page.locator(selector).first.wait_for(state="visible", timeout=timeout)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        elif self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._session_cleared = False

    def __enter__(self) -> Browser:
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _ensure_page(self) -> Page:
        if self._page is None:
            self.open()
        assert self._page is not None
        return self._page

    def _locate(self, selector: str) -> Locator:
        page = self._ensure_page()
        candidates = [
            page.get_by_test_id(selector),
            page.get_by_label(selector, exact=False),
            page.get_by_placeholder(selector, exact=False),
            page.get_by_role("textbox", name=selector, exact=False),
            page.get_by_role("button", name=selector, exact=False),
            page.get_by_role("link", name=selector, exact=False),
            page.get_by_text(selector, exact=False),
            page.locator(selector),
        ]
        return self._first_match(candidates, selector)

    def _locate_fillable(self, selector: str) -> Locator:
        page = self._ensure_page()
        candidates = [
            page.get_by_label(selector, exact=False),
            page.get_by_placeholder(selector, exact=False),
            page.get_by_test_id(selector),
            page.get_by_role("textbox", name=selector, exact=False),
            page.locator(selector),
        ]
        return self._first_match(candidates, selector)

    def _locate_clickable(self, selector: str) -> Locator:
        page = self._ensure_page()
        candidates = [
            page.get_by_role("button", name=selector, exact=False),
            page.get_by_role("link", name=selector, exact=False),
            page.get_by_test_id(selector),
            page.get_by_text(selector, exact=True),
            page.locator(selector),
        ]
        return self._first_match(candidates, selector)

    def _first_match(self, candidates: list[Locator], selector: str) -> Locator:
        for locator in candidates:
            try:
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        raise ValueError(f"No matching element for: {selector}")
