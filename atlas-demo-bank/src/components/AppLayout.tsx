import { Navigate, Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useBank } from '../utils/bank'

export function AppLayout() {
  const { currentMember } = useBank()

  if (!currentMember) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="min-h-screen md:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <main className="px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
