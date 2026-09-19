from __future__ import annotations

import json
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from app.agent.act import act as run_act
from app.agent.record import record as run_record
from app.agent.safety import safety_check
from app.agent.schema import AgentAction
from app.agent.state import AgentState
from app.plan import is_transfer_goal, parse_transfer_goal, plan_query
from app.browser.manager import BrowserManager
from app.run.logger import RunLogger

SYSTEM_PROMPT = """You are a computer-use agent controlling Atlas Bank in a real browser.

Supported tasks:
1. Open a Checking or Savings account
2. Account balance lookup
3. Transfer funds between Savings and Checking
4. Create a monthly transaction statement
5. Delete an account only through the confirmed delete_account flow

Each turn you see the current page observation. Choose exactly one action:
- navigate: target is a URL
- fill: target is a visible field label such as Username, Password, From Account, To Account, or Amount; value is the text to type or the dropdown option
- click: target is a visible button or link such as Sign In, Open Checking Account, Open Savings Account, Transfer Money, Review Transfer, Confirm Transfer, Dashboard, or Transactions
- read: target is a test id or visible label such as savings-account, checking-account, open-account-message, transfer-id, or transactions
- finish: value is the final answer for the user
- request_human: use this if you are stuck

The LLM must not generate Playwright code. Choose an action schema only.

Rules:
- Do not invent balances, transfer IDs, or amounts. Only report numbers from the page observation or a read result.
- Sign in first if the page is a login form.
- If the current page is already Dashboard, Transfer, or Transactions, you are signed in. Do not navigate to login again.
- For opening an account: after login, on the dashboard fill Account name and Use (Personal or Business), then click Open Checking Account or Open Savings Account. Atlas Bank generates the account ID. You may hold one Checking and one Savings account only; if both already exist, finish that additional accounts are not allowed. If that account card is already visible and the Open button is not, the account exists — finish with that.
- For a balance lookup: after login, go to the dashboard if needed, read the requested account, then finish.
- For a transfer: after login, click Transfer Money, fill From Account, To Account, and Amount, click Review Transfer, click Confirm Transfer, click Transactions, read transaction-table, then finish. Report only the debit and credit rows for that transfer (Date, Description, Account, Amount, Type, Status). Do not keep transferring.
- For a monthly statement: after login, click Transactions, read transaction-table, then finish. Do not invent transactions.
- Never click Delete. Account deletions are handled by a separate confirmed flow, not by this agent.
- Prefer labels the user can see: Username, Password, Sign In, Account name, Use, Open Checking Account, Open Savings Account, Transfer Money, From Account, To Account, Amount, Review Transfer, Confirm Transfer, transfer-id, Transactions, Dashboard, savings-account, checking-account, open-account-message, transaction-table.
"""


def build_llm() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    return ChatGroq(model=model, temperature=0, api_key=api_key)


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM did not return an action JSON object.")
    return match.group(0)


async def _choose_action(state: AgentState) -> AgentAction:
    observation = state.get("observation") or {"url": "", "title": "", "text": ""}
    task_hint = ""
    goal = state["goal"]
    tasks = plan_query(goal)
    current = tasks[0] if tasks else None
    if current and current.kind == "open_account":
        account = current.params.get("account") or "Checking"
        task_hint = f"""
This task is to open a {account} account.
Account name: {current.params.get("account_name") or account}
Use: {current.params.get("account_use") or "Personal"}
Do not ask for or fill an Account ID; the bank generates it.
On the dashboard fill Account name and Use, then click Open {account} Account.
If both Checking and Savings accounts are already on the dashboard, finish: You already have Checking and Savings accounts. Additional accounts are not allowed.
If {account} Account is already on the dashboard and Open {account} Account is not, finish: {account} account already exists.
Do not transfer funds and do not look up a different account.
"""
    elif is_transfer_goal(goal):
        parsed = parse_transfer_goal(goal)
        task_hint = f"""
This is a funds transfer.
From Account: {parsed["from_account"]}
To Account: {parsed["to_account"]}
Amount: {parsed["amount"]}
Memo: {parsed["memo"] or "(leave blank)"}
Follow the transfer flow once. Do not look up a balance instead.
After Confirm Transfer, click Transactions, read transaction-table, then finish with only the matching debit and credit rows.
"""
    elif current and current.kind == "get_balance":
        account = current.params.get("account") or "Savings"
        task_hint = f"""
This is a balance lookup for the {account} account.
After login, read {account.lower()}-account, then finish with that balance.
Do not open an account and do not transfer funds.
"""
    prompt = f"""Goal: {state["goal"]}
{task_hint}
Bank URL: {os.getenv("BANK_URL", "http://127.0.0.1:5173/login")}
Username: {os.getenv("BANK_USERNAME", "alex")}
Password: {os.getenv("BANK_PASSWORD", "atlas123")}

Iteration: {state["iteration"]} / {state["max_iterations"]}
Action log: {state.get("action_log") or []}
Last action result: {state.get("last_result")}
Risk of last action: {state.get("risk_level")}
Checkpoints: {state.get("checkpoints") or {}}

Current page:
URL: {observation.get("url")}
Title: {observation.get("title")}
Text:
{str(observation.get("text") or "")[:5000]}

Return the next AgentAction.
"""
    llm = build_llm()
    try:
        structured = llm.with_structured_output(AgentAction)
        action = await structured.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        if isinstance(action, AgentAction):
            return action
    except Exception:
        pass

    raw = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt + "\nRespond with JSON only."),
        ]
    )
    content = raw.content if isinstance(raw.content, str) else json.dumps(raw.content)
    return AgentAction.model_validate_json(_extract_json(content))


def _shortcut_action(state: AgentState) -> AgentAction | None:
    tasks = plan_query(state.get("goal") or "")
    if not tasks or tasks[0].kind != "open_account":
        return None
    account = tasks[0].params.get("account") or "Checking"
    observation = state.get("observation") or {}
    text = str(observation.get("text") or "")
    url = str(observation.get("url") or "")
    last = str(state.get("last_result") or "")
    on_app = any(part in url for part in ("/dashboard", "/transfer", "/transactions")) or "Welcome back" in text
    if not on_app:
        return None
    clicked_open = "Clicked" in last and f"Open {account}" in last
    open_button = f"Open {account} Account" in text
    both_exist = (
        "/dashboard" in url
        and "Open Checking Account" not in text
        and "Open Savings Account" not in text
    )
    if "already exists" in last.lower() or "account opened" in last.lower() or "additional accounts" in last.lower():
        return AgentAction(action="finish", value=last, reason="open account complete")
    if clicked_open:
        if open_button:
            return AgentAction(
                action="read",
                target="open-account-message",
                reason="confirm the account was opened",
            )
        return AgentAction(
            action="finish",
            value=f"{account} account opened.",
            reason="open account complete",
        )
    if both_exist:
        return AgentAction(
            action="finish",
            value="You already have Checking and Savings accounts. Additional accounts are not allowed.",
            reason="both accounts already exist",
        )
    if open_button:
        log = " ".join(state.get("action_log") or []).lower()
        params = tasks[0].params
        if "account name" not in log:
            return AgentAction(
                action="fill",
                target="Account name",
                value=params.get("account_name") or account,
                reason="set account name",
            )
        if "fill use " not in log and not log.endswith("use"):
            return AgentAction(
                action="fill",
                target="Use",
                value=params.get("account_use") or "Personal",
                reason="set personal or business use",
            )
        return AgentAction(
            action="click",
            target=f"Open {account} Account",
            reason="open the requested account",
        )
    if f"{account} Account" in text:
        return AgentAction(
            action="finish",
            value=f"{account} account already exists.",
            reason="account already open",
        )
    if "/dashboard" not in url:
        return AgentAction(action="click", target="Dashboard", reason="open accounts from the dashboard")
    return None


def build_agent(browser_manager: BrowserManager, run_logger: RunLogger | None = None):
    async def observe(state: AgentState):
        page = await browser_manager.open()
        observation = {
            "url": page.url,
            "title": await page.title(),
            "text": await page.locator("body").inner_text(),
        }
        print(f"[observe] {observation['url']} ({observation['title']})")
        if run_logger is not None:
            run_logger.log_observe(observation["url"], observation["title"])
        return {
            "observation": observation,
            "iteration": state.get("iteration", 0) + 1,
            "status": "observing",
        }

    async def decide(state: AgentState):
        if state.get("iteration", 0) >= state.get("max_iterations", 18):
            action = AgentAction(
                action="finish",
                value="Stopped after the maximum number of browser steps.",
                reason="max_iterations",
            )
        else:
            action = _shortcut_action(state) or await _choose_action(state)
        print(f"[decide] {action.action} target={action.target} value={action.value}")
        dumped = action.model_dump()
        if run_logger is not None:
            run_logger.log_llm_decision(dumped)
        updates = {
            "action": dumped,
            "status": "deciding",
        }
        if action.action == "finish":
            updates["answer"] = action.value or action.reason or ""
            updates["status"] = "done"
        if action.action == "request_human":
            updates["answer"] = action.reason or action.value or "Human help is needed."
            updates["status"] = "needs_human"
        return updates

    def safety(state: AgentState):
        return safety_check(state)

    async def act(state: AgentState):
        result = await run_act(state, browser_manager)
        if run_logger is not None:
            run_logger.log_act(state.get("action") or {})
        return result

    async def record(state: AgentState):
        return await run_record(state, browser_manager, run_logger)

    def route_after_safety(state: AgentState) -> str:
        if state.get("status") == "blocked":
            return END
        action = (state.get("action") or {}).get("action")
        if action in {"finish", "request_human"}:
            return "record"
        return "act"

    def route_after_record(state: AgentState) -> str:
        action = (state.get("action") or {}).get("action")
        if action in {"finish", "request_human"}:
            return END
        if state.get("iteration", 0) >= state.get("max_iterations", 18):
            return END
        return "observe"

    graph = StateGraph(AgentState)
    graph.add_node("observe", observe)
    graph.add_node("decide", decide)
    graph.add_node("safety", safety)
    graph.add_node("act", act)
    graph.add_node("record", record)
    graph.add_edge(START, "observe")
    graph.add_edge("observe", "decide")
    graph.add_edge("decide", "safety")
    graph.add_conditional_edges(
        "safety",
        route_after_safety,
        {"act": "act", "record": "record", END: END},
    )
    graph.add_edge("act", "record")
    graph.add_conditional_edges(
        "record",
        route_after_record,
        {"observe": "observe", END: END},
    )
    return graph.compile()
