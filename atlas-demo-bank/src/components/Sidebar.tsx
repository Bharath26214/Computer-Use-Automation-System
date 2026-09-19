import { NavLink } from 'react-router-dom'
import { useBank } from '../utils/bank'

const links = [
  { to: '/dashboard', label: 'Dashboard', testId: 'nav-dashboard' },
  { to: '/transactions', label: 'Transactions', testId: 'nav-transactions' },
  { to: '/transfer', label: 'Transfer Money', testId: 'nav-transfer' },
]

export function Sidebar() {
  const { currentMember, logout } = useBank()

  return (
    <aside className="flex w-full flex-col bg-atlas-navy text-white md:min-h-screen md:w-64">
      <div className="border-b border-white/10 px-5 py-6">
        <p className="text-xs uppercase tracking-[0.22em] text-atlas-gold">Personal Banking</p>
        <p className="mt-2 text-xl font-semibold">Atlas Bank</p>
        {currentMember ? (
          <p className="mt-3 text-sm text-slate-200" data-testid="signed-in-member">
            {currentMember.fullName}
          </p>
        ) : null}
      </div>
      <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 p-3">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            data-testid={link.testId}
            className={({ isActive }) =>
              `rounded-md px-3 py-2.5 text-sm font-medium ${
                isActive ? 'bg-white/15 text-white' : 'text-slate-200 hover:bg-white/10'
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-white/10 p-4">
        <button
          type="button"
          data-testid="sign-out"
          onClick={logout}
          className="w-full rounded-md border border-white/20 px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/10"
        >
          Sign Out
        </button>
      </div>
    </aside>
  )
}
