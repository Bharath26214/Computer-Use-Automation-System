import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'
import { useBank } from '../utils/bank'

export function Login() {
  const { currentMember, login } = useBank()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  if (currentMember) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <AuthShell title="Sign In">
      <form
        data-testid="login"
        noValidate
        className="mt-6 space-y-5"
        onSubmit={(event) => {
          event.preventDefault()
          if (!username.trim()) {
            setError('Username is required.')
            return
          }
          if (!password) {
            setError('Password is required.')
            return
          }
          const message = login(username, password)
          if (message) {
            setError(message)
            return
          }
          navigate('/dashboard')
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
            value={username}
            onChange={(event) => {
              setUsername(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            name="password"
            data-testid="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
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
