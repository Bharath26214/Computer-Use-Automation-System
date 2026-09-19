import { useMemo, useState } from 'react'
import { TransactionTable } from '../components/TransactionTable'
import { useBank } from '../utils/bank'
import { sortTransactionsByDate } from '../utils/format'

export function Transactions() {
  const { transactions } = useBank()
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const sorted = sortTransactionsByDate(transactions)
    const needle = query.trim().toLowerCase()
    if (!needle) {
      return sorted
    }
    return sorted.filter((transaction) =>
      transaction.description.toLowerCase().includes(needle),
    )
  }, [query, transactions])

  return (
    <section data-testid="transactions">
      <h1 className="text-2xl font-semibold text-atlas-navy">Transactions</h1>
      <p className="mt-1 text-sm text-slate-500">Search and review account activity</p>

      <div className="my-6 max-w-md">
        <label htmlFor="transaction-search" className="mb-1.5 block text-sm font-medium">
          Search transactions
        </label>
        <input
          id="transaction-search"
          data-testid="transaction-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5"
        />
      </div>

      <TransactionTable transactions={filtered} />
    </section>
  )
}
