import { initialAccounts, type Account } from './accounts'
import { initialTransactions, type Transaction } from './transactions'

/** Post-login demo scenarios exercised by the computer-use agent. */
export type LoginScenario =
  | 'normal'
  | 'page_not_found'
  | 'reloading'
  | 'hard_failure'

export type Member = {
  id: string
  fullName: string
  username: string
  password: string
  accounts: Account[]
  transactions: Transaction[]
  /** Demo-only: which login fault path this member triggers. */
  loginScenario?: LoginScenario
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

export const SEED_PASSWORD = ''

const sharedAccounts = (): Account[] => clone(initialAccounts)
const sharedTx = (): Transaction[] => clone(initialTransactions)

/**
 * Scenario users for error-handling demos:
 * 1. alex123     — normal login
 * 2. casey404    — page not found, then details after reload
 * 3. taylor321   — reloading after username
 * 4. blake000    — hard failure after retries (no other errors)
 */
export const seedMembers: Member[] = [
  {
    id: 'member-alex',
    fullName: 'Alex Rivera',
    username: 'alex123',
    password: SEED_PASSWORD,
    loginScenario: 'normal',
    accounts: sharedAccounts(),
    transactions: sharedTx(),
  },
  {
    id: 'member-casey',
    fullName: 'Casey Novak',
    username: 'casey404',
    password: SEED_PASSWORD,
    loginScenario: 'page_not_found',
    accounts: sharedAccounts(),
    transactions: sharedTx(),
  },
  {
    id: 'member-taylor',
    fullName: 'Taylor Brooks',
    username: 'taylor321',
    password: SEED_PASSWORD,
    loginScenario: 'reloading',
    accounts: sharedAccounts(),
    transactions: sharedTx(),
  },
  {
    id: 'member-blake',
    fullName: 'Blake Ortiz',
    username: 'blake000',
    password: SEED_PASSWORD,
    loginScenario: 'hard_failure',
    accounts: sharedAccounts(),
    transactions: sharedTx(),
  },
]

export function postLoginPath(scenario: LoginScenario | undefined): string {
  switch (scenario) {
    case 'page_not_found':
      return '/not-found'
    case 'reloading':
      return '/reloading'
    case 'hard_failure':
      return '/unavailable'
    case 'normal':
    default:
      return '/dashboard'
  }
}
