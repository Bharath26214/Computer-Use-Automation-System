import { initialAccounts, type Account } from './accounts'
import { initialTransactions, type Transaction } from './transactions'

export type Member = {
  id: string
  fullName: string
  username: string
  password: string
  accounts: Account[]
  transactions: Transaction[]
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export const SEED_PASSWORD = 'atlas123'

export const seedMembers: Member[] = [
  {
    id: 'member-alex',
    fullName: 'Alex Rivera',
    username: 'alex',
    password: SEED_PASSWORD,
    accounts: clone(initialAccounts),
    transactions: clone(initialTransactions),
  },
  {
    id: 'member-jordan',
    fullName: 'Jordan Hale',
    username: 'jordan',
    password: SEED_PASSWORD,
    accounts: [
      {
        id: 'checking',
        accountId: 'CHK-6104',
        name: 'Checking',
        use: 'personal',
        maskedNumber: '****6104',
        balance: 2180.4,
      },
    ],
    transactions: clone(initialTransactions).filter((item) => item.account === 'Checking'),
  },
  {
    id: 'member-sam',
    fullName: 'Sam Chen',
    username: 'sam',
    password: SEED_PASSWORD,
    accounts: [
      {
        id: 'savings',
        accountId: 'SAV-3391',
        name: 'Savings',
        use: 'personal',
        maskedNumber: '****3391',
        balance: 8450.0,
      },
    ],
    transactions: [
      {
        transactionId: 'TXN001',
        date: '2026-09-10',
        description: 'Interest',
        account: 'Savings',
        amount: 18.2,
        type: 'Credit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN002',
        date: '2026-09-01',
        description: 'Transfer from Checking',
        account: 'Savings',
        amount: 400.0,
        type: 'Credit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN003',
        date: '2026-08-15',
        description: 'Quarterly Interest',
        account: 'Savings',
        amount: 22.1,
        type: 'Credit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN004',
        date: '2026-08-01',
        description: 'Savings Deposit',
        account: 'Savings',
        amount: 1000.0,
        type: 'Credit',
        status: 'Completed',
      },
    ],
  },
  {
    id: 'member-riley',
    fullName: 'Riley Patel',
    username: 'riley',
    password: SEED_PASSWORD,
    accounts: [
      {
        id: 'checking',
        accountId: 'CHK-7742',
        name: 'Checking',
        use: 'personal',
        maskedNumber: '****7742',
        balance: 1025.5,
      },
      {
        id: 'savings',
        accountId: 'SAV-2288',
        name: 'Savings',
        use: 'personal',
        maskedNumber: '****2288',
        balance: 3600.0,
      },
    ],
    transactions: [
      {
        transactionId: 'TXN001',
        date: '2026-09-14',
        description: 'Payroll',
        account: 'Checking',
        amount: 1875.0,
        type: 'Credit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN002',
        date: '2026-09-13',
        description: 'Starbucks',
        account: 'Checking',
        amount: -6.15,
        type: 'Debit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN003',
        date: '2026-09-12',
        description: 'Amazon',
        account: 'Checking',
        amount: -54.99,
        type: 'Debit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN004',
        date: '2026-09-08',
        description: 'Transfer to Savings',
        account: 'Checking',
        amount: -200.0,
        type: 'Debit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN005',
        date: '2026-09-08',
        description: 'Transfer from Checking',
        account: 'Savings',
        amount: 200.0,
        type: 'Credit',
        status: 'Completed',
      },
      {
        transactionId: 'TXN006',
        date: '2026-09-05',
        description: 'Interest',
        account: 'Savings',
        amount: 6.4,
        type: 'Credit',
        status: 'Completed',
      },
    ],
  },
]
