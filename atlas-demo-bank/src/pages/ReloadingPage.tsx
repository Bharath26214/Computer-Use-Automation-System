import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'

/** taylor321: show Reloading… long enough for 2s then 5s agent retries, then open. */
const RELOAD_MS = 7500

export function ReloadingPage() {
  const navigate = useNavigate()
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const tick = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000))
    }, 250)
    const done = window.setTimeout(() => {
      navigate('/dashboard', { replace: true })
    }, RELOAD_MS)
    return () => {
      window.clearInterval(tick)
      window.clearTimeout(done)
    }
  }, [navigate])

  return (
    <AuthShell title="Reloading">
      <div data-testid="reloading" className="mt-6 space-y-3">
        <p className="text-sm font-medium text-slate-800">Reloading…</p>
        <p className="text-sm text-slate-600">Please wait while we refresh your session.</p>
        <p className="text-xs text-slate-500" data-testid="reloading-elapsed">
          Still loading ({elapsed}s)
        </p>
      </div>
    </AuthShell>
  )
}
