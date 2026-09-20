import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AuthShell } from '../components/AuthShell'
import { useBank } from '../utils/bank'

export function Register() {
  const { currentMember, register } = useBank()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [openChecking, setOpenChecking] = useState(true)
  const [openSavings, setOpenSavings] = useState(false)
  const [error, setError] = useState('')

  if (currentMember) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <AuthShell title="Create Account">
      <form
        data-testid="register"
        noValidate
        className="mt-6 space-y-5"
        onSubmit={(event) => {
          event.preventDefault()
          const message = register({
            fullName,
            username,
            openChecking,
            openSavings,
          })
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
          <label htmlFor="full-name" className="mb-1.5 block text-sm font-medium">
            Full Name
          </label>
          <input
            id="full-name"
            name="fullName"
            data-testid="full-name"
            value={fullName}
            onChange={(event) => {
              setFullName(event.target.value)
              setError('')
            }}
            className="w-full rounded-md border border-slate-300 px-3 py-2.5"
          />
        </div>

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
            Letters followed by exactly three digits.
          </p>
        </div>

        <fieldset className="rounded-md border border-slate-200 p-3">
          <legend className="px-1 text-sm font-medium">Accounts to open</legend>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              data-testid="open-checking"
              checked={openChecking}
              onChange={(event) => {
                setOpenChecking(event.target.checked)
                setError('')
              }}
            />
            Checking
          </label>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              data-testid="open-savings"
              checked={openSavings}
              onChange={(event) => {
                setOpenSavings(event.target.checked)
                setError('')
              }}
            />
            Savings
          </label>
        </fieldset>

        <button
          type="submit"
          data-testid="create-account"
          className="w-full rounded-md bg-atlas-teal px-4 py-3 text-sm font-semibold text-white hover:bg-[#1a5f67]"
        >
          Create Account
        </button>
      </form>
      <p className="mt-4 text-sm text-slate-600">
        Already a member?{' '}
        <Link to="/login" data-testid="go-to-login" className="font-semibold text-atlas-teal">
          Sign In
        </Link>
      </p>
    </AuthShell>
  )
}
