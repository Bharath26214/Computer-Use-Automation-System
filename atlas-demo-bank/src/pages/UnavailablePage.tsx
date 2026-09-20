import { Link } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'

/**
 * blake000: hard failure that survives reload — no other recoverable errors.
 * Agent retries once then must stop with cannot recover.
 */
export function UnavailablePage() {
  return (
    <AuthShell title="Unavailable">
      <div data-testid="hard-failure" className="mt-6 space-y-4">
        <p className="text-sm font-medium text-slate-800">Cannot be recovered</p>
        <p className="text-sm text-slate-700">
          Atlas Bank services are unavailable for this member. Reloading will not help.
        </p>
        <p className="text-xs text-slate-500" data-testid="hard-failure-detail">
          Hard failure after retrying — remove all other error paths for this user.
        </p>
        <Link
          to="/login"
          data-testid="back-to-login"
          className="inline-block text-sm font-semibold text-atlas-teal"
        >
          Back to Sign In
        </Link>
      </div>
    </AuthShell>
  )
}
