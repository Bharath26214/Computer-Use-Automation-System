from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.plan.transfer_goal import extract_amount, is_transfer_goal, parse_transfer_goal

LOOKUP_BALANCE = "lookup_balance"
TRANSFER_FUNDS = "transfer_funds"
OPEN_ACCOUNT = "open_account"
DELETE_ACCOUNT = "delete_account"
CREATE_STATEMENT = "create_statement"

CLAUSE_SPLIT = re.compile(
    r"\b(?:then|and then|after that|afterwards|afterward|;)\b",
    re.IGNORECASE,
)
AND_SPLIT = re.compile(r"\s+\band\s+\b", re.IGNORECASE)

CREATE_STATEMENT_RE = re.compile(
    r"\b(?:create|generate|make|get|download|print|prepare|show)\b.{0,40}\bstatements?\b"
    r"|\bmonthly\s+statements?\b"
    r"|\bstatements?\s+for\b"
    r"|\btransaction\s+statements?\b",
    re.IGNORECASE,
)
MONTH_NAMES = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
DELETE_CHECKING = re.compile(
    r"(?:delete|clos(?:e|ing)|remov(?:e|ing))\b(?:(?!\b(?:savings|transfer)\b).){0,24}\bchecking\b"
    r"|\bchecking\b.{0,24}(?:account)?.{0,12}(?:delete|close|remove)",
    re.IGNORECASE,
)
DELETE_SAVINGS = re.compile(
    r"(?:delete|clos(?:e|ing)|remov(?:e|ing))\b(?:(?!\b(?:checking|transfer)\b).){0,24}\bsavings\b"
    r"|\bsavings\b.{0,24}(?:account)?.{0,12}(?:delete|close|remove)",
    re.IGNORECASE,
)
DELETE_GENERIC = re.compile(
    r"\b(?:delete|clos(?:e|ing)|remov(?:e|ing))\b(?!.*\b(?:checking|savings)\b).{0,24}\baccounts?\b",
    re.IGNORECASE,
)
OPEN_CHECKING = re.compile(
    r"(?:open|add(?:ing)?|make)\b(?:(?!\b(?:savings|transfer|statement)\b).){0,24}\bchecking\b"
    r"|(?:creat(?:e|ing))\b(?:(?!\b(?:savings|transfer|statement)\b).){0,24}\bchecking\b\s+account"
    r"|\bchecking\b.{0,16}(?:account).{0,12}(?:open|creat)",
    re.IGNORECASE,
)
OPEN_SAVINGS = re.compile(
    r"(?:open|add(?:ing)?|make)\b(?:(?!\b(?:checking|transfer|statement)\b).){0,24}\bsavings\b"
    r"|(?:creat(?:e|ing))\b(?:(?!\b(?:checking|transfer|statement)\b).){0,24}\bsavings\b\s+account"
    r"|\bsavings\b.{0,16}(?:account).{0,12}(?:open|creat)",
    re.IGNORECASE,
)
TRANSFER = re.compile(
    r"\b(?:transfer|send money|move money|wire)\b"
    r"|\bfrom\s+(?:savings|checking)\s+to\s+(?:savings|checking)\b",
    re.IGNORECASE,
)
_LOOKUP = r"(?:look up|display|show|read|get|what(?:'s| is)?|how much(?: is)?(?: in)?)"
SAVINGS_BALANCE = re.compile(
    rf"(?:{_LOOKUP}\b.{{0,40}}\bsavings"
    r"|\bsavings\b(?:\s+account)?\s+balance"
    r"|\bbalance\b.{0,20}\bsavings)",
    re.IGNORECASE,
)
CHECKING_BALANCE = re.compile(
    rf"(?:{_LOOKUP}\b.{{0,40}}\bchecking"
    r"|\bchecking\b(?:\s+account)?\s+balance"
    r"|\bbalance\b.{0,20}\bchecking)",
    re.IGNORECASE,
)
ACCOUNT_NAME_RE = re.compile(
    r"(?:named|account\s+name\b|\bname\b)\s*(?:is|:)?\s*['\"]?(.+?)['\"]?(?=\s*,|\s+use\b|\s+personal\b|\s+business\b|\s+then\b|\s+and then\b|$)",
    re.IGNORECASE,
)
USE_RE = re.compile(r"\b(personal|business)\b", re.IGNORECASE)


@dataclass
class PlannedTask:
    kind: str
    artifact_id: str
    goal: str
    params: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        if self.kind == "transfer":
            return "|".join(
                [
                    self.artifact_id,
                    self.params.get("from_account") or "",
                    self.params.get("to_account") or "",
                ]
            )
        if self.kind == "create_statement":
            return "|".join(
                [
                    self.artifact_id,
                    self.params.get("account") or "all",
                    self.params.get("month") or "",
                ]
            )
        return f"{self.artifact_id}|{self.params.get('account') or ''}"


def account_params(account: str) -> dict[str, str]:
    name = "Checking" if str(account).lower().startswith("check") else "Savings"
    key = name.lower()
    return {
        "account": name,
        "account_key": key,
        "account_testid": f"{key}-account",
        "account_name": name,
        "account_use": "Personal",
    }


def parse_month(query: str, today: date | None = None) -> str:
    now = today or date.today()
    text = query or ""
    iso = re.search(r"\b(20\d{2})-(\d{1,2})\b", text)
    if iso:
        return f"{iso.group(1)}-{int(iso.group(2)):02d}"
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else now.year
    for name, month in MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", text, re.IGNORECASE):
            return f"{year}-{month:02d}"
    return f"{now.year}-{now.month:02d}"


def parse_statement_fields(query: str) -> dict[str, str]:
    text = query or ""
    params = {"month": parse_month(text)}
    lowered = text.lower()
    has_checking = bool(re.search(r"\bchecking\b", lowered))
    has_savings = bool(re.search(r"\bsavings\b", lowered))
    if has_checking and not has_savings:
        params.update(account_params("Checking"))
    elif has_savings and not has_checking:
        params.update(account_params("Savings"))
    return params


def _create_statement(query: str = "", account: str = "") -> PlannedTask:
    params = parse_statement_fields(query)
    if account:
        params.update(account_params(account))
        params["month"] = parse_month(query)
    label = params.get("account") or "all accounts"
    month = params.get("month") or parse_month(query)
    return PlannedTask(
        "create_statement",
        CREATE_STATEMENT,
        f"Create a {month} statement for {label}",
        params,
    )


def parse_open_fields(query: str, account: str) -> dict[str, str]:
    params = account_params(account)
    text = query or ""
    name_match = ACCOUNT_NAME_RE.search(text)
    use_match = USE_RE.search(text)
    if name_match:
        params["account_name"] = name_match.group(1).strip(" .,'\"")
    if use_match:
        params["account_use"] = use_match.group(1).title()
    return params


def _open_account(account: str, query: str = "") -> PlannedTask:
    params = parse_open_fields(query, account)
    return PlannedTask(
        "open_account",
        OPEN_ACCOUNT,
        (
            f"Open a {params['account']} account named {params['account_name']} "
            f"use {params['account_use']}"
        ),
        params,
    )


def _delete_account(account: str) -> PlannedTask:
    if str(account).lower().startswith("check"):
        params = account_params("Checking")
        params["other_account"] = "Savings"
    elif str(account).lower().startswith("sav"):
        params = account_params("Savings")
        params["other_account"] = "Checking"
    else:
        params = {"account": "", "other_account": ""}
        return PlannedTask("delete_account", DELETE_ACCOUNT, "Delete an account", params)
    return PlannedTask(
        "delete_account",
        DELETE_ACCOUNT,
        f"Delete the {params['account']} account",
        params,
    )


def _open_checking() -> PlannedTask:
    return _open_account("Checking")


def _open_savings() -> PlannedTask:
    return _open_account("Savings")


def _transfer(query: str) -> PlannedTask:
    parsed = parse_transfer_goal(query)
    amount = parsed.get("amount") or ""
    goal = (
        f"Transfer {amount} from {parsed['from_account']} to {parsed['to_account']}"
        if amount
        else f"Transfer from {parsed['from_account']} to {parsed['to_account']}"
    )
    return PlannedTask("transfer", TRANSFER_FUNDS, goal, parsed)


def _lookup_balance(account: str) -> PlannedTask:
    params = account_params(account)
    return PlannedTask(
        "get_balance",
        LOOKUP_BALANCE,
        f"What is my {params['account'].lower()} account balance?",
        params,
    )


def _savings_balance() -> PlannedTask:
    return _lookup_balance("Savings")


def _checking_balance() -> PlannedTask:
    return _lookup_balance("Checking")


def classify_clause(clause: str, full_query: str = "") -> PlannedTask | None:
    text = clause or ""
    if DELETE_CHECKING.search(text):
        return _delete_account("Checking")
    if DELETE_SAVINGS.search(text):
        return _delete_account("Savings")
    if DELETE_GENERIC.search(text):
        return _delete_account("")
    if CREATE_STATEMENT_RE.search(text):
        return _create_statement(full_query or text)
    if OPEN_CHECKING.search(text):
        return _open_account("Checking", full_query or text)
    if OPEN_SAVINGS.search(text):
        return _open_account("Savings", full_query or text)
    if TRANSFER.search(text) or is_transfer_goal(text):
        task = _transfer(full_query or text)
        if not task.params.get("amount"):
            amount = extract_amount(full_query or text)
            if amount:
                task.params["amount"] = amount
                task.goal = (
                    f"Transfer {amount} from {task.params['from_account']} "
                    f"to {task.params['to_account']}"
                )
        return task
    if SAVINGS_BALANCE.search(text):
        return _savings_balance()
    if CHECKING_BALANCE.search(text):
        return _checking_balance()
    return None


def _scan_intents(query: str) -> list[PlannedTask]:
    found: list[tuple[int, PlannedTask]] = []
    mapping = [
        (DELETE_CHECKING, lambda: _delete_account("Checking")),
        (DELETE_SAVINGS, lambda: _delete_account("Savings")),
        (DELETE_GENERIC, lambda: _delete_account("")),
        (CREATE_STATEMENT_RE, lambda: _create_statement(query)),
        (OPEN_CHECKING, lambda: _open_account("Checking", query)),
        (OPEN_SAVINGS, lambda: _open_account("Savings", query)),
        (TRANSFER, lambda: _transfer(query)),
        (SAVINGS_BALANCE, _savings_balance),
        (CHECKING_BALANCE, _checking_balance),
    ]
    for pattern, factory in mapping:
        match = pattern.search(query or "")
        if match:
            found.append((match.start(), factory()))
    found.sort(key=lambda item: item[0])
    tasks: list[PlannedTask] = []
    seen: set[str] = set()
    for _start, task in found:
        if task.key in seen:
            continue
        seen.add(task.key)
        tasks.append(task)
    amount = extract_amount(query)
    for task in tasks:
        if task.kind == "create_statement":
            task.params.update(parse_statement_fields(query))
            account = task.params.get("account") or "all accounts"
            month = task.params.get("month") or parse_month(query)
            task.goal = f"Create a {month} statement for {account}"
        if task.kind == "open_account":
            task.params.update(parse_open_fields(query, task.params.get("account") or "Checking"))
        if task.kind == "transfer" and amount:
            task.params["amount"] = amount
            task.goal = (
                f"Transfer {amount} from {task.params['from_account']} "
                f"to {task.params['to_account']}"
            )
    return tasks


def plan_query(query: str) -> list[PlannedTask]:
    text = (query or "").strip()
    if not text:
        return [_savings_balance()]

    scanned = _scan_intents(text)
    if len(scanned) > 1:
        return scanned

    clauses = [part.strip() for part in CLAUSE_SPLIT.split(text) if part.strip()]
    expanded: list[str] = []
    for clause in clauses:
        pieces = [part.strip() for part in AND_SPLIT.split(clause) if part.strip()]
        if len(pieces) > 1 and all(classify_clause(piece, text) for piece in pieces):
            expanded.extend(pieces)
        else:
            expanded.append(clause)

    tasks: list[PlannedTask] = []
    seen: set[str] = set()
    for clause in expanded:
        task = classify_clause(clause, text)
        if task is None:
            continue
        if task.key in seen:
            continue
        seen.add(task.key)
        tasks.append(task)

    if not tasks:
        if scanned:
            return scanned
        if is_transfer_goal(text):
            return [_transfer(text)]
        if CREATE_STATEMENT_RE.search(text) or "statement" in text.lower():
            return [_create_statement(text)]
        if "checking" in text.lower():
            return [_checking_balance()]
        return [_savings_balance()]
    return tasks


def is_open_account_goal(goal: str) -> bool:
    text = goal or ""
    return bool(OPEN_CHECKING.search(text) or OPEN_SAVINGS.search(text))


def is_delete_account_goal(goal: str) -> bool:
    text = goal or ""
    return bool(
        DELETE_CHECKING.search(text)
        or DELETE_SAVINGS.search(text)
        or DELETE_GENERIC.search(text)
    )


def is_create_statement_goal(goal: str) -> bool:
    text = goal or ""
    return bool(CREATE_STATEMENT_RE.search(text) or "statement" in text.lower())
