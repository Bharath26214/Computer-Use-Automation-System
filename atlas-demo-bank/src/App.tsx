import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { MfaPage } from './pages/MfaPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { Register } from './pages/Register'
import { ReloadingPage } from './pages/ReloadingPage'
import { Transactions } from './pages/Transactions'
import { Transfer } from './pages/Transfer'
import { UnavailablePage } from './pages/UnavailablePage'
import { BankProvider } from './utils/bank'

export default function App() {
  return (
    <BrowserRouter>
      <BankProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/not-found" element={<NotFoundPage />} />
          <Route path="/mfa" element={<MfaPage />} />
          <Route path="/reloading" element={<ReloadingPage />} />
          <Route path="/unavailable" element={<UnavailablePage />} />
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/transfer" element={<Transfer />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BankProvider>
    </BrowserRouter>
  )
}
