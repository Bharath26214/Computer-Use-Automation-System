# Atlas Bank

Fictional local banking website.

## Run

```bash
npm install
npm run dev
```

Open the local Vite URL. Start at `/login`.

## Sample members

Password for seeded members: `atlas123`

| Member | Username | Accounts |
| --- | --- | --- |
| Alex Rivera | alex | Checking + Savings |
| Jordan Hale | jordan | Checking |
| Sam Chen | sam | Savings |
| Riley Patel | riley | Checking + Savings |

You can also create a new member on `/register` and choose Checking, Savings, or both. After signing in, members who only have one account can open the missing Checking or Savings account from the dashboard.

## Pages

- `/login`
- `/register`
- `/dashboard`
- `/transactions`
- `/transfer`

Member data is stored in browser `localStorage`.
