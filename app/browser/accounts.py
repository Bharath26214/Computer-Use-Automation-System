from __future__ import annotations

import os
import re

from app.browser.manager import BrowserManager

CURRENCY = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")


def product_key(account: str) -> str:
    text = (account or "").strip().lower()
    if text.startswith("check"):
        return "checking"
    if text.startswith("sav"):
        return "savings"
    return text


def missing_account_message(account: str) -> str:
    name = "Checking" if product_key(account) == "checking" else "Savings"
    return f"You do not have a {name} account."


async def _accounts_from_storage(page) -> list[dict]:
    """
    Read open products from atlas-bank.members.v3 without leaving the current route.

    Needed on /transfer and /transactions where dashboard account cards are not in the DOM.
    """
    try:
        accounts = await page.evaluate(
            """() => {
              try {
                const sessionId = localStorage.getItem('atlas-bank.session');
                if (!sessionId) return [];
                const raw =
                  localStorage.getItem('atlas-bank.members.v3') ||
                  localStorage.getItem('atlas-bank.members.v2') ||
                  localStorage.getItem('atlas-bank.members');
                if (!raw) return [];
                const members = JSON.parse(raw);
                const match = Array.isArray(members)
                  ? members.find((member) => member && member.id === sessionId)
                  : null;
                return (match && Array.isArray(match.accounts)) ? match.accounts : [];
              } catch (e) {
                return [];
              }
            }"""
        )
    except Exception:
        return []
    if not isinstance(accounts, list):
        return []
    return [item for item in accounts if isinstance(item, dict)]


async def account_is_open(browser_manager: BrowserManager, account: str) -> bool:
    page = browser_manager.page
    if page is None:
        return False
    key = product_key(account)
    if key not in {"checking", "savings"}:
        return False
    open_id = f"{key}-account"
    missing_id = f"missing-{key}-account"
    try:
        await page.locator(
            f'[data-testid="{open_id}"], [data-testid="{missing_id}"]'
        ).first.wait_for(state="visible", timeout=1500)
    except Exception:
        pass
    try:
        if await page.get_by_test_id(open_id).count() > 0:
            return True
    except Exception:
        pass

    # Transfer / transactions pages omit account cards — use member storage.
    for item in await _accounts_from_storage(page):
        item_id = str(item.get("id") or "").strip().lower()
        if item_id == key:
            return True
    return False


async def ensure_dashboard(browser_manager: BrowserManager) -> None:
    page = await browser_manager.open()
    url = page.url or ""
    if "/dashboard" not in url:
        try:
            await page.get_by_test_id("nav-dashboard").click(timeout=3000)
            await page.wait_for_load_state("networkidle")
        except Exception:
            bank = os.getenv("BANK_URL", "http://localhost:5173/login")
            origin = bank
            for suffix in ("/login", "/dashboard", "/transfer", "/transactions", "/register"):
                if origin.endswith(suffix):
                    origin = origin[: -len(suffix)] or origin
                    break
            origin = origin.rstrip("/") or "http://localhost:5173"
            await page.goto(f"{origin}/dashboard", wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
    try:
        await page.get_by_test_id("dashboard").wait_for(state="visible", timeout=8000)
    except Exception:
        pass


async def _session_username(page) -> str | None:
    try:
        username = await page.evaluate(
            """() => {
              try {
                const sessionId = localStorage.getItem('atlas-bank.session');
                if (!sessionId) return null;
                const raw =
                  localStorage.getItem('atlas-bank.members.v3') ||
                  localStorage.getItem('atlas-bank.members.v2') ||
                  localStorage.getItem('atlas-bank.members');
                if (!raw) return null;
                const members = JSON.parse(raw);
                const match = Array.isArray(members)
                  ? members.find((member) => member && member.id === sessionId)
                  : null;
                return match && match.username ? String(match.username) : null;
              } catch (e) {
                return null;
              }
            }"""
        )
    except Exception:
        return None
    if not username:
        return None
    return str(username).strip()


async def ensure_signed_in(
    browser_manager: BrowserManager,
    skip_auth: bool = False,
    run_logger=None,
) -> None:
    page = await browser_manager.open()
    wanted = (os.getenv("BANK_USERNAME", "alex123") or "alex123").strip()
    from app.artifact.recorder import expected_error_kind_for_member

    # Scenario members must always re-login so 404/MFA/reload gates fire and
    # get recorded on the discovery artifact (persistent browser profile).
    scenario_kind = expected_error_kind_for_member(wanted)
    current = await _session_username(page)
    url = page.url or ""
    on_app = any(part in url for part in ("/dashboard", "/transfer", "/transactions"))
    if (
        scenario_kind is None
        and current
        and current.lower() == wanted.lower()
        and on_app
    ):
        return
    if (
        scenario_kind is None
        and skip_auth
        and current
        and current.lower() == wanted.lower()
        and on_app
    ):
        return

    bank_url = os.getenv("BANK_URL", "http://localhost:5173/login")
    if not str(bank_url).endswith("/login"):
        origin = str(bank_url)
        for suffix in (
            "/login",
            "/dashboard",
            "/transfer",
            "/transactions",
            "/register",
            "/not-found",
            "/mfa",
            "/reloading",
            "/unavailable",
        ):
            if origin.endswith(suffix):
                origin = origin[: -len(suffix)] or origin
                break
        bank_url = (origin.rstrip("/") or "http://localhost:5173") + "/login"

    await page.goto(bank_url, wait_until="domcontentloaded")
    # Drop a stale session so Sign In always targets BANK_USERNAME.
    # Also reset scenario gates (404 one-shot) so casey404 etc. always fire.
    await page.evaluate(
        """() => {
          try { localStorage.removeItem('atlas-bank.session'); } catch (e) {}
          try {
            for (const key of Object.keys(sessionStorage)) {
              if (key.startsWith('atlas-bank.scenario.')) sessionStorage.removeItem(key);
            }
          } catch (e) {}
        }"""
    )
    await page.reload(wait_until="domcontentloaded")
    await page.get_by_label("Username").fill(wanted)
    login_button = page.get_by_role("button", name=re.compile(r"^(Sign In|Log In)$", re.I))
    await login_button.click()
    await page.wait_for_load_state("networkidle")

    # Surface invalid member IDs as a classified run failure.
    try:
        alert = await page.get_by_role("alert").inner_text(timeout=2000)
    except Exception:
        alert = ""
    if alert and any(token in alert.lower() for token in ("invalid", "not found", "unknown")):
        raise RuntimeError("Username not found")

    # Scenario users land on 404 / MFA / reloading / hard-failure gates.
    from app.errors.recover import resolve_login_scenario_gates
    from app.errors.types import RecoveryStatus

    gate = await resolve_login_scenario_gates(page, run_logger=run_logger)
    if gate is not None and gate.status in {
        RecoveryStatus.FAILED,
        RecoveryStatus.TERMINAL,
        RecoveryStatus.REJECTED,
    }:
        raise RuntimeError(gate.message)

    try:
        await page.get_by_test_id("signed-in-member").wait_for(state="visible", timeout=12000)
    except Exception:
        still_login = "/login" in (page.url or "")
        if still_login:
            raise RuntimeError("Username not found")
        raise RuntimeError(
            f"UI changed: signed-in member chrome did not appear after login "
            f"(browser is on {page.url})"
        )


async def read_account_balance(browser_manager: BrowserManager, account: str) -> float | None:
    """
    Prefer dashboard DOM; if mid-flow on another route, read balance from member storage
    so transfer discovery is not yanked back to the dashboard.
    """
    page = browser_manager.page
    key = product_key(account)
    if page is not None:
        url = page.url or ""
        on_dashboard = "/dashboard" in url
        if not on_dashboard:
            for item in await _accounts_from_storage(page):
                if str(item.get("id") or "").strip().lower() == key:
                    try:
                        return round(float(item.get("balance")), 2)
                    except (TypeError, ValueError):
                        break

    await ensure_dashboard(browser_manager)
    page = browser_manager.page
    if page is None or not await account_is_open(browser_manager, account):
        return None
    try:
        text = await page.get_by_test_id(f"{key}-account").inner_text()
    except Exception:
        return None
    match = CURRENCY.search(text or "")
    if not match:
        return None
    return round(float(match.group(1).replace(",", "")), 2)
