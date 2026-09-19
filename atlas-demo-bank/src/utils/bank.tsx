import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Account, AccountUse } from '../data/accounts'
import { productName } from '../data/accounts'
import type { Member } from '../data/members'
import type { Transaction } from '../data/transactions'
import {
  generateTransferId,
  nextTransactionId,
  roundMoney,
  todayISODate,
} from './format'
import {
  clearSession,
  loadMembers,
  loadSessionId,
  saveMembers,
  saveSessionId,
  seedMembersIfNeeded,
  upsertMember,
} from './storage'

export type TransferResult = {
  transferId: string
  fromAccount: string
  toAccount: string
  amount: number
  memo: string
}

export type RegisterInput = {
  fullName: string
  username: string
  password: string
  openChecking: boolean
  openSavings: boolean
}

export type OpenAccountDetails = {
  name: string
  use: AccountUse
}

type BankContextValue = {
  currentMember: Member | null
  accounts: Account[]
  transactions: Transaction[]
  login: (username: string, password: string) => string | null
  register: (input: RegisterInput) => string | null
  logout: () => void
  openAccount: (
    accountName: 'Checking' | 'Savings',
    details?: OpenAccountDetails,
  ) => string | null
  deleteAccount: (accountName: 'Checking' | 'Savings') => string | null
  completeTransfer: (
    fromName: string,
    toName: string,
    amount: number,
    memo: string,
  ) => TransferResult
}

const BankContext = createContext<BankContextValue | null>(null)

function randomLast4(): string {
  return String(Math.floor(1000 + Math.random() * 9000))
}

function generateAccountId(accountName: 'Checking' | 'Savings', accounts: Account[]): string {
  const prefix = accountName === 'Checking' ? 'CHK' : 'SAV'
  const existing = new Set(accounts.map((account) => account.accountId))
  let accountId = `${prefix}-${randomLast4()}`
  while (existing.has(accountId)) {
    accountId = `${prefix}-${randomLast4()}`
  }
  return accountId
}

function createAccount(
  accountName: 'Checking' | 'Savings',
  details?: OpenAccountDetails,
  accounts: Account[] = [],
): Account {
  const id = accountName === 'Checking' ? 'checking' : 'savings'
  return {
    id,
    accountId: generateAccountId(accountName, accounts),
    name: details?.name.trim() || accountName,
    use: details?.use === 'business' ? 'business' : 'personal',
    maskedNumber: `****${randomLast4()}`,
    balance: accountName === 'Checking' ? 500.0 : 250.0,
  }
}

function findProductAccount(accounts: Account[], productOrName: string): Account | undefined {
  const key = productOrName.trim().toLowerCase()
  return accounts.find(
    (account) =>
      account.id === key ||
      productName(account).toLowerCase() === key ||
      account.name.toLowerCase() === key,
  )
}

function openingAccounts(openChecking: boolean, openSavings: boolean): Account[] {
  const accounts: Account[] = []
  if (openChecking) {
    accounts.push(createAccount('Checking', undefined, accounts))
  }
  if (openSavings) {
    accounts.push(createAccount('Savings', undefined, accounts))
  }
  return accounts
}

function openingTransactions(accounts: Account[]): Transaction[] {
  return accounts.map((account, index) => ({
    transactionId: `TXN${String(index + 1).padStart(3, '0')}`,
    date: todayISODate(),
    description: 'Opening Deposit',
    account: account.name,
    amount: account.balance,
    type: 'Credit',
    status: 'Completed',
  }))
}

export function BankProvider({ children }: { children: ReactNode }) {
  const [members, setMembers] = useState<Member[]>(() => seedMembersIfNeeded())
  const [currentMember, setCurrentMember] = useState<Member | null>(() => {
    const sessionId = loadSessionId()
    if (!sessionId) {
      return null
    }
    return loadMembers().find((member) => member.id === sessionId) ?? null
  })

  const value = useMemo<BankContextValue>(() => {
    return {
      currentMember,
      accounts: currentMember?.accounts ?? [],
      transactions: currentMember?.transactions ?? [],
      login(username, password) {
        const latestMembers = loadMembers()
        const match = latestMembers.find(
          (member) =>
            member.username.toLowerCase() === username.trim().toLowerCase() &&
            member.password === password,
        )
        if (!match) {
          return 'Invalid username or password.'
        }
        setMembers(latestMembers)
        saveSessionId(match.id)
        setCurrentMember(match)
        return null
      },
      register(input) {
        const latestMembers = loadMembers()
        const fullName = input.fullName.trim()
        const username = input.username.trim().toLowerCase()
        const password = input.password
        if (!fullName) {
          return 'Full name is required.'
        }
        if (!username) {
          return 'Username is required.'
        }
        if (!password) {
          return 'Password is required.'
        }
        if (!input.openChecking && !input.openSavings) {
          return 'Select at least one account to open.'
        }
        if (latestMembers.some((member) => member.username.toLowerCase() === username)) {
          return 'That username is already in use.'
        }

        const accounts = openingAccounts(input.openChecking, input.openSavings)
        const created: Member = {
          id: `member-${Date.now()}`,
          fullName,
          username,
          password,
          accounts,
          transactions: openingTransactions(accounts),
        }
        const nextMembers = upsertMember(latestMembers, created)
        saveMembers(nextMembers)
        saveSessionId(created.id)
        setMembers(nextMembers)
        setCurrentMember(created)
        return null
      },
      logout() {
        clearSession()
        setCurrentMember(null)
      },
      openAccount(accountName, details) {
        const latestMembers = loadMembers()
        const member =
          latestMembers.find((item) => item.id === currentMember?.id) ?? currentMember
        if (!member) {
          return 'You must be signed in to open an account.'
        }
        const hasChecking = member.accounts.some((account) => account.id === 'checking')
        const hasSavings = member.accounts.some((account) => account.id === 'savings')
        if (hasChecking && hasSavings) {
          return 'You already have Checking and Savings accounts. Additional accounts are not allowed.'
        }
        const productId = accountName === 'Checking' ? 'checking' : 'savings'
        if (member.accounts.some((account) => account.id === productId)) {
          return `You already have a ${accountName} account.`
        }
        if (!details?.name.trim()) {
          return 'Account name is required.'
        }

        const account = createAccount(accountName, details, member.accounts)
        const transactionId = nextTransactionId(
          member.transactions.map((item) => item.transactionId),
        )
        const updated: Member = {
          ...member,
          accounts: [...member.accounts, account],
          transactions: [
            {
              transactionId,
              date: todayISODate(),
              description: 'Opening Deposit',
              account: account.name,
              amount: account.balance,
              type: 'Credit',
              status: 'Completed',
            },
            ...member.transactions,
          ],
        }
        const nextMembers = upsertMember(latestMembers, updated)
        saveMembers(nextMembers)
        setMembers(nextMembers)
        setCurrentMember(updated)
        return null
      },
      deleteAccount(accountName) {
        const latestMembers = loadMembers()
        const member =
          latestMembers.find((item) => item.id === currentMember?.id) ?? currentMember
        if (!member) {
          return 'You must be signed in to delete an account.'
        }
        const productId = accountName === 'Checking' ? 'checking' : 'savings'
        const account = member.accounts.find((item) => item.id === productId)
        if (!account) {
          return `You do not have a ${accountName} account.`
        }
        if (roundMoney(account.balance) > 0) {
          return `${accountName} cannot be deleted with a nonzero balance.`
        }
        const updated: Member = {
          ...member,
          accounts: member.accounts.filter((item) => item.id !== productId),
        }
        const nextMembers = upsertMember(latestMembers, updated)
        saveMembers(nextMembers)
        setMembers(nextMembers)
        setCurrentMember(updated)
        return null
      },
      completeTransfer(fromName, toName, amount, memo) {
        const latestMembers = loadMembers()
        const member =
          latestMembers.find((item) => item.id === currentMember?.id) ?? currentMember
        if (!member) {
          throw new Error('You must be signed in to transfer money.')
        }
        const source = findProductAccount(member.accounts, fromName)
        const destination = findProductAccount(member.accounts, toName)
        if (!source || !destination) {
          throw new Error('Source and destination accounts must be different.')
        }

        const nextAccounts = member.accounts.map((account) => {
          if (account.id === source.id) {
            return { ...account, balance: roundMoney(account.balance - amount) }
          }
          if (account.id === destination.id) {
            return { ...account, balance: roundMoney(account.balance + amount) }
          }
          return account
        })

        const debitId = nextTransactionId(member.transactions.map((item) => item.transactionId))
        const creditId = nextTransactionId([
          ...member.transactions.map((item) => item.transactionId),
          debitId,
        ])
        const date = todayISODate()
        const debitDescription = memo
          ? `Transfer to ${toName} - ${memo}`
          : `Transfer to ${toName}`
        const creditDescription = memo
          ? `Transfer from ${fromName} - ${memo}`
          : `Transfer from ${fromName}`

        const updated: Member = {
          ...member,
          accounts: nextAccounts,
          transactions: [
            {
              transactionId: debitId,
              date,
              description: debitDescription,
              account: fromName,
              amount: -amount,
              type: 'Debit',
              status: 'Completed',
            },
            {
              transactionId: creditId,
              date,
              description: creditDescription,
              account: toName,
              amount,
              type: 'Credit',
              status: 'Completed',
            },
            ...member.transactions,
          ],
        }

        const nextMembers = upsertMember(latestMembers, updated)
        saveMembers(nextMembers)
        setMembers(nextMembers)
        setCurrentMember(updated)

        return {
          transferId: generateTransferId(),
          fromAccount: fromName,
          toAccount: toName,
          amount,
          memo,
        }
      },
    }
  }, [currentMember, members])

  return <BankContext.Provider value={value}>{children}</BankContext.Provider>
}

export function useBank(): BankContextValue {
  const context = useContext(BankContext)
  if (!context) {
    throw new Error('useBank must be used within BankProvider')
  }
  return context
}
