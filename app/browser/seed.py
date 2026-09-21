"""Restore Atlas demo member products to seed balances (browser localStorage)."""

from __future__ import annotations

# Keep in sync with atlas-demo-bank/src/data/accounts.ts initialAccounts.
SEED_ACCOUNTS = [
    {
        "id": "checking",
        "accountId": "CHK-4521",
        "name": "Checking",
        "use": "personal",
        "maskedNumber": "****4521",
        "balance": 4250.75,
    },
    {
        "id": "savings",
        "accountId": "SAV-7812",
        "name": "Savings",
        "use": "personal",
        "maskedNumber": "****7812",
        "balance": 12800.0,
    },
]


async def reset_member_accounts_to_seed(page, username: str) -> bool:
    """
    Replace the signed-in / named member's accounts with seed Checking+Savings.
    Used by discovery harness so transfer/delete cases are not blocked by a
    prior delete left in persistent browser localStorage.
    """
    if page is None:
        return False
    wanted = (username or "").strip().lower()
    if not wanted:
        return False
    try:
        ok = await page.evaluate(
            """({ username, accounts }) => {
              try {
                const raw =
                  localStorage.getItem('atlas-bank.members.v3') ||
                  localStorage.getItem('atlas-bank.members.v2') ||
                  localStorage.getItem('atlas-bank.members');
                if (!raw) return false;
                const members = JSON.parse(raw);
                if (!Array.isArray(members)) return false;
                const idx = members.findIndex(
                  (m) => m && String(m.username || '').toLowerCase() === username
                );
                if (idx < 0) return false;
                members[idx] = {
                  ...members[idx],
                  accounts: JSON.parse(JSON.stringify(accounts)),
                  transactions: Array.isArray(members[idx].transactions)
                    ? members[idx].transactions
                    : [],
                };
                localStorage.setItem(
                  'atlas-bank.members.v3',
                  JSON.stringify(members)
                );
                return true;
              } catch (e) {
                return false;
              }
            }""",
            {"username": wanted, "accounts": SEED_ACCOUNTS},
        )
    except Exception:
        return False
    return bool(ok)
