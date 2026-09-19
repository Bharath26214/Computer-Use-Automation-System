export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount)
}

export function formatSignedCurrency(amount: number): string {
  const formatted = formatCurrency(Math.abs(amount))
  if (amount > 0) {
    return `+${formatted}`
  }
  if (amount < 0) {
    return `-${formatted}`
  }
  return formatted
}

export function roundMoney(amount: number): number {
  return Math.round(amount * 100) / 100
}

export function todayISODate(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function generateTransferId(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  let suffix = ''
  for (let i = 0; i < 6; i += 1) {
    suffix += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return `TRF-${suffix}`
}

export function nextTransactionId(existingIds: string[]): string {
  let max = 0
  for (const id of existingIds) {
    const match = /^TXN(\d+)$/.exec(id)
    if (match) {
      max = Math.max(max, Number(match[1]))
    }
  }
  return `TXN${String(max + 1).padStart(3, '0')}`
}

export function sortTransactionsByDate<T extends { date: string; transactionId: string }>(
  transactions: T[],
): T[] {
  return [...transactions].sort((a, b) => {
    if (a.date !== b.date) {
      return b.date.localeCompare(a.date)
    }
    return a.transactionId.localeCompare(b.transactionId)
  })
}
