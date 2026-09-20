import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'

const RETRY_KEY = 'atlas-bank.scenario.404-state'

/**
 * casey404: first visit shows Page not found; after one reload, open the dashboard.
 */
export function NotFoundPage() {
  const navigate = useNavigate()

  useEffect(() => {
    const state = sessionStorage.getItem(RETRY_KEY)
    if (state === 'pending') {
      sessionStorage.setItem(RETRY_KEY, 'recovered')
      navigate('/dashboard', { replace: true })
      return
    }
    // First paint — next page.reload() from the agent should recover.
    sessionStorage.setItem(RETRY_KEY, 'pending')
  }, [navigate])

  return (
    <AuthShell title="Page not found">
      <div data-testid="page-not-found" className="mt-6 space-y-4">
        <p className="text-sm text-slate-700">
          404 — Page not found. The member portal could not be loaded.
        </p>
        <p className="text-xs text-slate-500">
          Reload this page once to continue to your account details.
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
