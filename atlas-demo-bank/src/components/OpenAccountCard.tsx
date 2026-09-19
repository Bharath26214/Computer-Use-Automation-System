import { useState } from 'react'
import type { AccountUse } from '../data/accounts'

export type OpenAccountDetails = {
  name: string
  use: AccountUse
}

type OpenAccountCardProps = {
  accountName: 'Checking' | 'Savings'
  onOpen: (details: OpenAccountDetails) => void
}

export function OpenAccountCard({ accountName, onOpen }: OpenAccountCardProps) {
  const slug = accountName.toLowerCase()
  const [name, setName] = useState<string>(accountName)
  const [use, setUse] = useState<AccountUse>('personal')
  const [error, setError] = useState('')

  return (
    <form
      data-testid={`missing-${slug}-account`}
      className="flex flex-col justify-between rounded-xl border border-dashed border-slate-300 bg-white p-6"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        if (!name.trim()) {
          setError('Account name is required.')
          return
        }
        onOpen({
          name: name.trim(),
          use,
        })
      }}
    >
      <div>
        <h2 className="text-lg font-semibold text-atlas-navy">Open {accountName} Account</h2>
        <p className="mt-2 text-sm text-slate-500">
          You can hold one Checking account and one Savings account. Choose a name and personal or
          business use. Atlas Bank assigns the account ID.
        </p>
      </div>

      {error ? (
        <p role="alert" className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      <div className="mt-4 space-y-3">
        <div>
          <label htmlFor={`${slug}-account-name`} className="mb-1.5 block text-sm font-medium">
            Account name
          </label>
          <input
            id={`${slug}-account-name`}
            name="accountName"
            data-testid={`${slug}-account-name`}
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
        </div>
        <div>
          <label htmlFor={`${slug}-account-use`} className="mb-1.5 block text-sm font-medium">
            Use
          </label>
          <select
            id={`${slug}-account-use`}
            name="accountUse"
            data-testid={`${slug}-account-use`}
            value={use}
            onChange={(event) => setUse(event.target.value as AccountUse)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5"
          >
            <option value="personal">Personal</option>
            <option value="business">Business</option>
          </select>
        </div>
      </div>

      <button
        type="submit"
        data-testid={`open-${slug}-account`}
        className="mt-6 rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
      >
        Open {accountName} Account
      </button>
    </form>
  )
}
