import type { Account } from '../data/accounts'
import { productName } from '../data/accounts'
import { formatCurrency, roundMoney } from '../utils/format'

type AccountCardProps = {
  account: Account
  testId: string
  onDelete?: () => void
}

export function AccountCard({ account, testId, onDelete }: AccountCardProps) {
  const product = productName(account)
  const slug = product.toLowerCase()
  const canDelete = roundMoney(account.balance) === 0

  return (
    <article
      data-testid={testId}
      className="flex flex-col rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-atlas-navy">{account.name} Account</h2>
      <p className="mt-1 text-sm text-slate-500">
        {account.accountId} · {account.use === 'business' ? 'Business' : 'Personal'} ·{' '}
        {account.maskedNumber}
      </p>
      <p className="mt-6 text-3xl font-semibold tracking-tight text-atlas-navy">
        {formatCurrency(account.balance)}
      </p>
      {onDelete ? (
        <div className="mt-6">
          <button
            type="button"
            data-testid={`delete-${slug}-account`}
            disabled={!canDelete}
            title={
              canDelete
                ? `Delete ${product} account`
                : `${product} cannot be deleted with a nonzero balance.`
            }
            onClick={onDelete}
            className="rounded-md border border-red-300 px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400 disabled:hover:bg-transparent"
          >
            Delete {product} Account
          </button>
          {canDelete ? null : (
            <p className="mt-2 text-xs text-slate-500">
              Transfer the remaining balance before this account can be deleted.
            </p>
          )}
        </div>
      ) : null}
    </article>
  )
}
