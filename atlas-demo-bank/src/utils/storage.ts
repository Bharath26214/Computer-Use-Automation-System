import { seedMembers, type Member } from '../data/members'
import { normalizeAccount } from '../data/accounts'

const MEMBERS_KEY = 'atlas-bank.members.v3'
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
  // Ensure scenario demo users exist even if an older v3 blob was saved.
  const existing = loadMembers()
  let changed = false
  let merged = [...existing]
  for (const seed of seedMembers) {
    const index = merged.findIndex(
      (member) => member.username.toLowerCase() === seed.username.toLowerCase(),
    )
    if (index < 0) {
      merged = [...merged, normalizeMember(clone(seed))]
      changed = true
    } else if (!merged[index].loginScenario && seed.loginScenario) {
      merged[index] = {
        ...merged[index],
        loginScenario: seed.loginScenario,
      }
      changed = true
    }
  }
  if (changed) {
    saveMembers(merged)
  }
  return merged
}

export function upsertMember(members: Member[], updated: Member): Member[] {
  const exists = members.some((member) => member.id === updated.id)
  if (exists) {
    return members.map((member) => (member.id === updated.id ? updated : member))
  }
  return [...members, updated]
}
