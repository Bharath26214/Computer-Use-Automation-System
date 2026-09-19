export type AccountUse = 'personal' | 'business'

export type Account = {
  id: string
  accountId: string
  name: string
  use: AccountUse
  maskedNumber: string
  balance: number
}

export function productName(account: Account): 'Checking' | 'Savings' {
  return account.id === 'savings' ? 'Savings' : 'Checking'
}

export function normalizeAccount(account: Account): Account {
  const id = account.id === 'savings' ? 'savings' : 'checking'
  const product = id === 'savings' ? 'Savings' : 'Checking'
  const digits = account.maskedNumber?.replace(/\D/g, '') || '1001'
  return {
    id,
    accountId: account.accountId?.trim() || `${id === 'savings' ? 'SAV' : 'CHK'}-${digits}`,
    name: account.name || product,
    use: account.use === 'business' ? 'business' : 'personal',
    maskedNumber: account.maskedNumber,
    balance: account.balance,
  }
}

export const initialAccounts: Account[] = [
  {
    id: 'checking',
    accountId: 'CHK-4521',
    name: 'Checking',
    use: 'personal',
    maskedNumber: '****4521',
    balance: 4250.75,
  },
  {
    id: 'savings',
    accountId: 'SAV-7812',
    name: 'Savings',
    use: 'personal',
    maskedNumber: '****7812',
    balance: 12800.0,
  },
]
