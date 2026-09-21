# Atlas Demo Bank — setup

Local Vite + React stand-in for a back-office banking UI. Used as the live surface for discovery and replay. There is no backend; member state lives in browser `localStorage`.

## Prerequisites

- Node.js 18+

## Launch

```bash
cd atlas-demo-bank
npm install
npm run dev
```

Vite prints a local URL (usually `http://127.0.0.1:5173/`). Open `/login`.

Other scripts: `npm run build`, `npm run preview`, `npm run lint`.

## Seeded members

Password is empty for demo members (username-only sign-in).

| Username | Scenario | Purpose |
| --- | --- | --- |
| `alex123` | normal | Happy-path discovery and replay |
| `casey404` | page_not_found | Recoverable 404 after login |
| `taylor321` | reloading | Transient reloading gate |
| `blake000` | hard_failure | Unrecoverable failure after retry |

Each member is seeded with Checking and Savings unless a prior run deleted a product. The discovery harness can restore seed balances before lookup/transfer/delete cases.

## Pages

| Route | Role |
| --- | --- |
| `/login` | Sign in |
| `/register` | Create a member |
| `/dashboard` | Account cards, open/delete |
| `/transfer` | Transfer form → review → confirm |
| `/transactions` | Ledger |
| `/not-found`, `/reloading`, `/unavailable` | Scenario gates for casey404 / taylor321 / blake000 |

## Notes for automation

- Prefer `data-testid` attributes (`checking-account`, `open-savings-account`, `confirm-delete-savings`, …).
- Protected actions (delete, open, large transfer confirm) show an in-app confirmation page; the agent pauses for human click + `resume`, or `--yes` auto-clicks.
- Do not point this system at a real bank or use real credentials.
