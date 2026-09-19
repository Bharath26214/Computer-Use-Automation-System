import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AccountCard } from '../components/AccountCard'
import { OpenAccountCard, type OpenAccountDetails } from '../components/OpenAccountCard'
import { useBank } from '../utils/bank'
import { formatSignedCurrency, sortTransactionsByDate } from '../utils/format'

export function Dashboard() {
  const navigate = useNavigate()
  const { currentMember, accounts, transactions, openAccount, deleteAccount } = useBank()
  const [message, setMessage] = useState('')
  const [messageError, setMessageError] = useState(false)
  const checking = accounts.find((account) => account.id === 'checking')
  const savings = accounts.find((account) => account.id === 'savings')
  const recent = sortTransactionsByDate(transactions).slice(0, 5)

  function handleOpen(accountName: 'Checking' | 'Savings', details: OpenAccountDetails) {
    const error = openAccount(accountName, details)
    if (error) {
      setMessageError(true)
      setMessage(error)
      return
    }
    setMessageError(false)
    setMessage(`${details.name} account opened.`)
  }

  function handleDelete(accountName: 'Checking' | 'Savings') {
    const error = deleteAccount(accountName)
    if (error) {
      setMessageError(true)
      setMessage(error)
      return
    }
    setMessageError(false)
    setMessage(`${accountName} account deleted.`)
  }

  return (
    <section data-testid="dashboard">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-atlas-navy">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Welcome back, {currentMember?.fullName}
          </p>
        </div>
        <button
          type="button"
          data-testid="transfer-money"
          onClick={() => navigate('/transfer')}
          className="inline-flex rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
        >
          Transfer Money
        </button>
      </div>

      {message ? (
        <p
          role="status"
          data-testid="open-account-message"
          className={`mb-4 rounded-md px-3 py-2 text-sm ${
            messageError ? 'bg-red-50 text-red-800' : 'bg-emerald-50 text-emerald-800'
          }`}
        >
          {message}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {checking ? (
          <AccountCard
            account={checking}
            testId="checking-account"
            onDelete={() => handleDelete('Checking')}
          />
        ) : (
          <OpenAccountCard accountName="Checking" onOpen={(details) => handleOpen('Checking', details)} />
        )}
        {savings ? (
          <AccountCard
            account={savings}
            testId="savings-account"
            onDelete={() => handleDelete('Savings')}
          />
        ) : (
          <OpenAccountCard accountName="Savings" onOpen={(details) => handleOpen('Savings', details)} />
        )}
      </div>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-atlas-navy">Recent Transactions</h2>
        {recent.length === 0 ? (
          <p className="rounded-xl border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
            No recent transactions.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
            {recent.map((transaction) => (
              <li
                key={transaction.transactionId}
                className="flex items-center justify-between gap-4 px-4 py-3"
              >
                <span className="font-medium text-atlas-navy">{transaction.description}</span>
                <span
                  className={`font-medium ${
                    transaction.amount >= 0 ? 'text-emerald-700' : 'text-red-700'
                  }`}
                >
                  {formatSignedCurrency(transaction.amount)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  )
}
