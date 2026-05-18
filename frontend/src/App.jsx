import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import AppShell from './components/AppShell'
import client from './api/client'
import { useAuth } from './hooks/useAuth'
import { useQuercusStatus } from './hooks/useQuercusStatus'
import Acorn from './pages/Acorn'
import Chat from './pages/Chat'
import ChatHistory from './pages/ChatHistory'
import CourseDetail from './pages/CourseDetail'
import Dashboard from './pages/Dashboard'
import DegreePlanner from './pages/DegreePlanner'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'

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

function QuercusTokenRequired({ children }) {
  const { data, isLoading, error } = useQuercusStatus()

  if (isLoading) {
    return <div className="callback-screen">Loading…</div>
  }
  if (error) {
    return <div className="callback-screen">Failed to load Quercus status.</div>
  }
  if (!data?.hasToken) {
    return <Navigate to="/onboarding" replace />
  }
  return children
}

function QuercusTokenMissing({ children }) {
  const { data, isLoading, error } = useQuercusStatus()

  if (isLoading) {
    return <div className="callback-screen">Loading…</div>
  }
  if (error) {
    return <div className="callback-screen">Failed to load Quercus status.</div>
  }
  if (data?.hasToken) {
    return <Navigate to="/" replace />
  }
  return children
}

export default function App() {
  const { isAuthenticated, isReady } = useAuth()
  const queryClient = useQueryClient()

  // On every app load while logged in, fire a background request to keep the
  // Supabase dashboard snapshot current. This ensures incognito / new-device
  // loads always hit the fast Supabase layer instead of the full live fetch.
  useEffect(() => {
    if (!isReady || !isAuthenticated) return

    client.get('/api/courses/dashboard')
      .then(({ data }) => {
        queryClient.setQueryData(['dashboard'], data)
        // Warm each course's grade breakdown so the detail page is instant.
        // Staggered 400 ms apart to avoid flooding Quercus with simultaneous requests.
        ;(data.courses ?? []).forEach((course, index) => {
          setTimeout(() => {
            client.get(`/api/courses/${course.id}/grades`)
              .then(({ data: gradesData }) => {
                // Skip the update if any mutation is in flight to avoid clobbering
                // optimistic updates from grade-override mutations.
                if (queryClient.isMutating() > 0) return
                queryClient.setQueryData(['course-grades', String(course.id)], gradesData)
              })
              .catch(() => {})
          }, (index + 1) * 400)
        })
      })
      .catch(() => {})
  }, [isAuthenticated, isReady, queryClient])

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route
        path="/onboarding"
        element={
          <ProtectedRoute>
            <QuercusTokenMissing>
              <Onboarding />
            </QuercusTokenMissing>
          </ProtectedRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route
          path="/"
          element={
            <QuercusTokenRequired>
              <Dashboard />
            </QuercusTokenRequired>
          }
        />
        <Route
          path="/courses/:id"
          element={
            <QuercusTokenRequired>
              <CourseDetail />
            </QuercusTokenRequired>
          }
        />
        <Route
          path="/chat"
          element={
            <QuercusTokenRequired>
              <Chat />
            </QuercusTokenRequired>
          }
        />
        <Route
          path="/chat/history"
          element={
            <QuercusTokenRequired>
              <ChatHistory />
            </QuercusTokenRequired>
          }
        />
        <Route
          path="/chat/:conversationId"
          element={
            <QuercusTokenRequired>
              <Chat />
            </QuercusTokenRequired>
          }
        />
        <Route path="/acorn" element={<Acorn />} />
        <Route path="/degree-planner" element={<DegreePlanner />} />
      </Route>
    </Routes>
  )
}
