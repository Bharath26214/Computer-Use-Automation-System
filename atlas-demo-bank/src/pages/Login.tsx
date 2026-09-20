import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'
import { postLoginPath } from '../data/members'
import { useBank } from '../utils/bank'

const MEMBER_ID_RE = /^[A-Za-z]+\d{3}$/

export function Login() {
  const { currentMember, login, peekScenario } = useBank()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')

  if (currentMember) {
    const scenario = peekScenario?.(currentMember.username) ?? currentMember.loginScenario
    return <Navigate to={postLoginPath(scenario)} replace />
  }

  return (
    <AuthShell title="Sign In">
      <form
        data-testid="login"
        noValidate
        className="mt-6 space-y-5"
        onSubmit={(event) => {
          event.preventDefault()
          const memberId = username.trim()
          if (!memberId) {
            setError('Username is required.')
            return
          }
          if (!MEMBER_ID_RE.test(memberId)) {
            setError('Username must be a name followed by exactly three digits (example: alex123).')
            return
          }
          const message = login(memberId)
          if (message) {
            setError(message)
            return
          }
          const scenario = peekScenario?.(memberId)
          navigate(postLoginPath(scenario))
        }}
      >
        {error ? (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        ) : null}

        <div>
          <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
            Username
          </label>
          <input
            id="username"
            name="username"
            data-testid="username"
            autoComplete="username"
            placeholder="alex123"
            value={username}
            onChange={(event) => {
              setUsername(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
          <p className="mt-1.5 text-xs text-slate-500">
            Demo members: alex123 (normal), casey404 (404), taylor321 (reloading),
            blake000 (hard failure).
          </p>
        </div>

        <button
          type="submit"
          data-testid="sign-in"
          className="w-full rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
        >
          Sign In
        </button>
      </form>
      <p className="mt-4 text-sm text-slate-600">
        New to Atlas Bank?{' '}
        <Link to="/register" data-testid="go-to-register" className="font-semibold text-atlas-teal">
          Create Account
        </Link>
      </p>
    </AuthShell>
  )
}
