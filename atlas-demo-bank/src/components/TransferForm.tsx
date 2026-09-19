export type TransferFormValues = {
  fromAccount: string
  toAccount: string
  amount: string
  memo: string
}

type TransferFormProps = {
  values: TransferFormValues
  accounts: string[]
  errors: string[]
  onChange: (values: TransferFormValues) => void
  onReview: () => void
}

export function TransferForm({
  values,
  accounts,
  errors,
  onChange,
  onReview,
}: TransferFormProps) {
  return (
    <form
      data-testid="transfer-form"
      noValidate
      className="max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault()
        onReview()
      }}
    >
      <h1 className="text-2xl font-semibold text-atlas-navy">Transfer Money</h1>
      <p className="mt-2 text-sm text-slate-500">
        Move money between your Atlas Bank accounts.
      </p>

      {errors.length > 0 ? (
        <div className="mt-4 space-y-2" role="alert">
          {errors.map((error) => (
            <p key={error} className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          ))}
        </div>
      ) : null}

      <div className="mt-6 space-y-5">
        <div>
          <label htmlFor="from-account" className="mb-1.5 block text-sm font-medium">
            From Account
          </label>
          <select
            id="from-account"
            name="fromAccount"
            data-testid="from-account"
            value={values.fromAccount}
            onChange={(event) => onChange({ ...values, fromAccount: event.target.value })}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5"
          >
            {accounts.map((account) => (
              <option key={account} value={account}>
                {account}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="to-account" className="mb-1.5 block text-sm font-medium">
            To Account
          </label>
          <select
            id="to-account"
            name="toAccount"
            data-testid="to-account"
            value={values.toAccount}
            onChange={(event) => onChange({ ...values, toAccount: event.target.value })}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5"
          >
            {accounts.map((account) => (
              <option key={account} value={account}>
                {account}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="transfer-amount" className="mb-1.5 block text-sm font-medium">
            Amount
          </label>
          <input
            id="transfer-amount"
            name="amount"
            data-testid="transfer-amount"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.01"
            value={values.amount}
            onChange={(event) => onChange({ ...values, amount: event.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
        </div>

        <div>
          <label htmlFor="transfer-memo" className="mb-1.5 block text-sm font-medium">
            Memo
          </label>
          <input
            id="transfer-memo"
            name="memo"
            data-testid="transfer-memo"
            type="text"
            value={values.memo}
            onChange={(event) => onChange({ ...values, memo: event.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
        </div>
      </div>

      <button
        type="submit"
        data-testid="review-transfer"
        className="mt-6 w-full rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
      >
        Review Transfer
      </button>
    </form>
  )
}
