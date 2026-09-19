import { useEffect, useMemo, useState } from 'react'
import { TransferForm, type TransferFormValues } from '../components/TransferForm'
import { productName } from '../data/accounts'
import { useBank, type TransferResult } from '../utils/bank'
import { formatCurrency } from '../utils/format'

type Step = 'form' | 'review' | 'success'

function validateTransfer(
  values: TransferFormValues,
  availableBalance: number | undefined,
): string[] {
  const errors: string[] = []
  if (!values.fromAccount) {
    errors.push('From Account is required.')
  }
  if (!values.toAccount) {
    errors.push('To Account is required.')
  }
  if (values.fromAccount && values.toAccount && values.fromAccount === values.toAccount) {
    errors.push('Source and destination accounts must be different.')
  }

  const amount = Number(values.amount)
  if (values.amount.trim() === '' || Number.isNaN(amount) || amount <= 0) {
    errors.push('Please enter a valid transfer amount.')
  } else if (availableBalance !== undefined && amount > availableBalance) {
    errors.push(`Insufficient funds in ${values.fromAccount} account.`)
  }

  return errors
}

export function Transfer() {
  const { accounts, completeTransfer, openAccount } = useBank()
  const accountNames = accounts.map((account) => productName(account))
  const accountKey = accountNames.join('|')
  const missingAccount = accounts.some((account) => account.id === 'checking')
    ? accounts.some((account) => account.id === 'savings')
      ? null
      : 'Savings'
    : 'Checking'
  const [step, setStep] = useState<Step>('form')
  const [errors, setErrors] = useState<string[]>([])
  const [values, setValues] = useState<TransferFormValues>({
    fromAccount: accountNames[0] ?? '',
    toAccount: accountNames[1] ?? accountNames[0] ?? '',
    amount: '',
    memo: '',
  })
  const [result, setResult] = useState<TransferResult | null>(null)
  const sourceBalance = useMemo(() => {
    return accounts.find((account) => productName(account) === values.fromAccount)?.balance
  }, [accounts, values.fromAccount])

  useEffect(() => {
    if (accountNames.length < 2) {
      return
    }
    setValues((current) => ({
      ...current,
      fromAccount: accountNames.includes('Checking') ? 'Checking' : accountNames[0],
      toAccount: accountNames.includes('Savings') ? 'Savings' : accountNames[1],
    }))
  }, [accountKey])

  if (accountNames.length < 2 && missingAccount) {
    return (
      <section
        data-testid="transfer"
        className="max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-2xl font-semibold text-atlas-navy">Transfer Money</h1>
        <p className="mt-3 text-sm text-slate-600">
          Transfers require both a Checking account and a Savings account. You currently have{' '}
          {accountNames[0] ?? 'one account'}.
        </p>
        <button
          type="button"
          data-testid={
            missingAccount === 'Checking' ? 'open-checking-account' : 'open-savings-account'
          }
          onClick={() =>
            openAccount(missingAccount, {
              name: missingAccount,
              use: 'personal',
            })
          }
          className="mt-6 rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
        >
          Open {missingAccount} Account
        </button>
      </section>
    )
  }

  if (step === 'success' && result) {
    return (
      <section
        data-testid="transfer-success"
        className="max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-2xl font-semibold text-atlas-navy">Transfer Successful</h1>
        <dl className="mt-6 space-y-4 text-sm">
          <div>
            <dt className="font-medium text-slate-500">Transfer ID</dt>
            <dd data-testid="transfer-id" className="mt-1 text-lg font-semibold text-atlas-navy">
              {result.transferId}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">From</dt>
            <dd data-testid="transfer-from" className="mt-1">{result.fromAccount}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">To</dt>
            <dd data-testid="transfer-to" className="mt-1">{result.toAccount}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Amount</dt>
            <dd data-testid="transfer-amount-result" className="mt-1">{formatCurrency(result.amount)}</dd>
          </div>
        </dl>
        <p className="mt-6 text-sm text-slate-700">Your transfer has been completed.</p>
      </section>
    )
  }

  if (step === 'review') {
    const amount = Number(values.amount)
    return (
      <section
        data-testid="transfer-review"
        className="max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-2xl font-semibold text-atlas-navy">Transfer Review</h1>
        <dl className="mt-6 space-y-4 text-sm">
          <div>
            <dt className="font-medium text-slate-500">From Account</dt>
            <dd className="mt-1">{values.fromAccount}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">To Account</dt>
            <dd className="mt-1">{values.toAccount}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Amount</dt>
            <dd className="mt-1">{formatCurrency(amount)}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Memo</dt>
            <dd className="mt-1">{values.memo}</dd>
          </div>
        </dl>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            data-testid="back-transfer"
            onClick={() => setStep('form')}
            className="flex-1 rounded-md border border-slate-300 px-4 py-3 text-sm font-semibold text-atlas-navy hover:bg-slate-50"
          >
            Back
          </button>
          <button
            type="button"
            data-testid="confirm-transfer"
            onClick={() => {
              const nextErrors = validateTransfer(values, sourceBalance)
              if (nextErrors.length > 0) {
                setErrors(nextErrors)
                setStep('form')
                return
              }
              const nextResult = completeTransfer(
                values.fromAccount,
                values.toAccount,
                Number(values.amount),
                values.memo.trim(),
              )
              setResult(nextResult)
              setStep('success')
            }}
            className="flex-1 rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
          >
            Confirm Transfer
          </button>
        </div>
      </section>
    )
  }

  return (
    <section data-testid="transfer">
      <TransferForm
        values={values}
        accounts={accountNames}
        errors={errors}
        onChange={(next) => {
          setValues(next)
          setErrors([])
        }}
        onReview={() => {
          const nextErrors = validateTransfer(values, sourceBalance)
          setErrors(nextErrors)
          if (nextErrors.length === 0) {
            setStep('review')
          }
        }}
      />
    </section>
  )
}
