import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'

/**
 * morgan789: multi-factor / human-operator gate.
 * Agent asks a human; after approval it clicks Approve to open the dashboard.
 */
export function MfaPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<'pending' | 'rejected'>('pending')

  return (
    <AuthShell title="Human operator">
      <div data-testid="mfa-gate" className="mt-6 space-y-4">
        <p className="text-sm text-slate-800">
          Multi-factor authentication required. A human operator must approve this sign-in.
        </p>
        <p className="text-xs text-slate-500" data-testid="mfa-prompt">
          Human intervention required — approve or reject to continue.
        </p>
        {status === 'rejected' ? (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
            Human intervention: rejected. Sign-in was not completed.
          </p>
        ) : null}
        <div className="flex gap-3">
          <button
            type="button"
            data-testid="mfa-approve"
            className="rounded-md bg-atlas-teal px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1a5f67]"
            onClick={() => navigate('/dashboard', { replace: true })}
          >
            Approve
          </button>
          <button
            type="button"
            data-testid="mfa-reject"
            className="rounded-md border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700"
            onClick={() => setStatus('rejected')}
          >
            Reject
          </button>
        </div>
      </div>
    </AuthShell>
  )
}
