import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AccountCard } from '../components/AccountCard'
import { ConfirmAction } from '../components/ConfirmAction'
import { OpenAccountCard, type OpenAccountDetails } from '../components/OpenAccountCard'
import { useBank } from '../utils/bank'
import { formatCurrency, formatSignedCurrency, roundMoney, sortTransactionsByDate } from '../utils/format'

type PendingOpen = {
  accountName: 'Checking' | 'Savings'
  details: OpenAccountDetails
}

export function Dashboard() {
  const navigate = useNavigate()
  const { currentMember, accounts, transactions, openAccount, deleteAccount } = useBank()
  const [message, setMessage] = useState('')
  const [messageError, setMessageError] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<'Checking' | 'Savings' | null>(null)
  const [pendingTransferBeforeDelete, setPendingTransferBeforeDelete] = useState<
    'Checking' | 'Savings' | null
  >(null)
  const [pendingOpen, setPendingOpen] = useState<PendingOpen | null>(null)
  const checking = accounts.find((account) => account.id === 'checking')
  const savings = accounts.find((account) => account.id === 'savings')
  const recent = sortTransactionsByDate(transactions).slice(0, 5)

  function otherAccount(accountName: 'Checking' | 'Savings'): 'Checking' | 'Savings' {
    return accountName === 'Checking' ? 'Savings' : 'Checking'
  }

  function handleOpenRequest(accountName: 'Checking' | 'Savings', details: OpenAccountDetails) {
    setPendingDelete(null)
    setPendingTransferBeforeDelete(null)
    setPendingOpen({ accountName, details })
    setMessage('')
  }

  function handleDeleteRequest(accountName: 'Checking' | 'Savings') {
    setPendingOpen(null)
    setMessage('')
    const account = accounts.find((item) =>
      accountName === 'Checking' ? item.id === 'checking' : item.id === 'savings',
    )
    if (account && roundMoney(account.balance) > 0) {
      setPendingDelete(null)
      setPendingTransferBeforeDelete(accountName)
      return
    }
    setPendingTransferBeforeDelete(null)
    setPendingDelete(accountName)
  }

  function confirmOpen() {
    if (!pendingOpen) {
      return
    }
    const { accountName, details } = pendingOpen
    const error = openAccount(accountName, details)
    setPendingOpen(null)
    if (error) {
      setMessageError(true)
      setMessage(error)
      return
    }
    setMessageError(false)
    setMessage(`${details.name} account opened.`)
  }

  function confirmTransferBeforeDelete() {
    if (!pendingTransferBeforeDelete) {
      return
    }
    const accountName = pendingTransferBeforeDelete
    const other = otherAccount(accountName)
    setPendingTransferBeforeDelete(null)
    setMessageError(false)
    setMessage(
      `Transfer funds approved: move remaining ${accountName} balance to ${other}, then delete ${accountName}.`,
    )
  }

  function confirmDelete() {
    if (!pendingDelete) {
      return
    }
    const accountName = pendingDelete
    const error = deleteAccount(accountName)
    setPendingDelete(null)
    if (error) {
      setMessageError(true)
      setMessage(error)
      return
    }
    setMessageError(false)
    setMessage(`${accountName} account deleted.`)
  }

  const transferSource = pendingTransferBeforeDelete
    ? accounts.find((item) =>
        pendingTransferBeforeDelete === 'Checking' ? item.id === 'checking' : item.id === 'savings',
      )
    : null

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

      {pendingTransferBeforeDelete && transferSource ? (
        <ConfirmAction
          title="Transfer funds before delete?"
          body={`Your ${pendingTransferBeforeDelete} account has ${formatCurrency(transferSource.balance)}. Transfer the remaining balance to ${otherAccount(pendingTransferBeforeDelete)}, then delete the account?`}
          confirmTestId={`confirm-transfer-before-delete-${pendingTransferBeforeDelete.toLowerCase()}`}
          cancelTestId="confirm-cancel"
          confirmLabel="Yes"
          cancelLabel="No"
          onConfirm={confirmTransferBeforeDelete}
          onCancel={() => setPendingTransferBeforeDelete(null)}
        />
      ) : null}

      {pendingDelete ? (
        <ConfirmAction
          title={`Confirm Delete ${pendingDelete} Account`}
          body={`Are you sure you want to permanently delete your ${pendingDelete} account? This cannot be undone.`}
          confirmTestId={`confirm-delete-${pendingDelete.toLowerCase()}`}
          confirmLabel="Yes, Confirm"
          cancelLabel="No"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}

      {pendingOpen ? (
        <ConfirmAction
          title={`Confirm Open ${pendingOpen.accountName} Account`}
          body={`Open a ${pendingOpen.accountName} account named “${pendingOpen.details.name}” for ${pendingOpen.details.use} use?`}
          confirmTestId={`confirm-open-${pendingOpen.accountName.toLowerCase()}`}
          confirmLabel="Yes, Confirm"
          cancelLabel="No"
          onConfirm={confirmOpen}
          onCancel={() => setPendingOpen(null)}
        />
      ) : null}

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
            onDelete={() => handleDeleteRequest('Checking')}
          />
        ) : (
          <OpenAccountCard
            accountName="Checking"
            onOpen={(details) => handleOpenRequest('Checking', details)}
          />
        )}
        {savings ? (
          <AccountCard
            account={savings}
            testId="savings-account"
            onDelete={() => handleDeleteRequest('Savings')}
          />
        ) : (
          <OpenAccountCard
            accountName="Savings"
            onOpen={(details) => handleOpenRequest('Savings', details)}
          />
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
