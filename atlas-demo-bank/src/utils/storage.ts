import { seedMembers, type Member } from '../data/members'
import { normalizeAccount } from '../data/accounts'

const MEMBERS_KEY = 'atlas-bank.members'
const SESSION_KEY = 'atlas-bank.session'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function normalizeMember(member: Member): Member {
  return {
    ...member,
    accounts: member.accounts.map((account) => normalizeAccount(account)),
  }
}

export function loadMembers(): Member[] {
  try {
    const raw = localStorage.getItem(MEMBERS_KEY)
    if (!raw) {
      return clone(seedMembers).map(normalizeMember)
    }
    const parsed = JSON.parse(raw) as Member[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return clone(seedMembers).map(normalizeMember)
    }
    return parsed.map(normalizeMember)
  } catch {
    return clone(seedMembers).map(normalizeMember)
  }
}

export function saveMembers(members: Member[]): void {
  localStorage.setItem(MEMBERS_KEY, JSON.stringify(members))
}

export function loadSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function saveSessionId(memberId: string): void {
  localStorage.setItem(SESSION_KEY, memberId)
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
}

export function seedMembersIfNeeded(): Member[] {
  if (!localStorage.getItem(MEMBERS_KEY)) {
    const members = clone(seedMembers).map((member) => ({
      ...member,
      accounts: member.accounts.map((account) => normalizeAccount(account)),
    }))
    saveMembers(members)
    return members
  }
  return loadMembers()
}

export function upsertMember(members: Member[], updated: Member): Member[] {
  const exists = members.some((member) => member.id === updated.id)
  if (exists) {
    return members.map((member) => (member.id === updated.id ? updated : member))
  }
  return [...members, updated]
}
