import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import AppShell from './components/AppShell'
import { useAuth } from './hooks/useAuth'
import Acorn from './pages/Acorn'
import Chat from './pages/Chat'
import CourseDetail from './pages/CourseDetail'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'

function AuthCallbackPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { completeLogin } = useAuth()

  useEffect(() => {
    const token = new URLSearchParams(location.search).get('token')
    if (!token) {
      navigate('/login', { replace: true })
      return
    }
    completeLogin(token).catch(() => navigate('/login', { replace: true }))
  }, [completeLogin, location.search, navigate])

  return <div className="callback-screen">Completing sign in…</div>
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, isReady } = useAuth()

  if (!isReady) {
    return <div className="callback-screen">Loading…</div>
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

export default function App() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/courses/:id" element={<CourseDetail />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/acorn" element={<Acorn />} />
      </Route>
    </Routes>
  )
}
