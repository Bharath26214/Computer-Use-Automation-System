import type { Transaction } from '../data/transactions'
import { formatSignedCurrency } from '../utils/format'

type TransactionTableProps = {
  transactions: Transaction[]
}

export function TransactionTable({ transactions }: TransactionTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="transaction-table">
      <table className="min-w-full border-collapse text-left text-sm">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th scope="col" className="px-4 py-3 font-semibold">
              Date
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Description
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Account
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Amount
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Type
            </th>
            <th scope="col" className="px-4 py-3 font-semibold">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {transactions.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                No matching transactions.
              </td>
            </tr>
          ) : (
            transactions.map((transaction) => (
              <tr
                key={transaction.transactionId}
                    data-testid={`transaction-row-${transaction.transactionId}`}
                    data-date={transaction.date}
                    data-account={transaction.account}
                    className="border-t border-slate-100"
              >
                <td className="px-4 py-3 text-slate-600">{transaction.date}</td>
                <td className="px-4 py-3 font-medium text-atlas-navy">
                  {transaction.description}
                </td>
                <td className="px-4 py-3">{transaction.account}</td>
                <td
                  className={`px-4 py-3 font-medium ${
                    transaction.amount >= 0 ? 'text-emerald-700' : 'text-red-700'
                  }`}
                >
                  {formatSignedCurrency(transaction.amount)}
                </td>
                <td className="px-4 py-3">{transaction.type}</td>
                <td className="px-4 py-3">{transaction.status}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
