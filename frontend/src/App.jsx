import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import AppShell from './components/AppShell'
import DemoShell from './components/DemoShell'
import client from './api/client'
import { DemoDataProvider } from './context/DemoDataContext'
import { useAuth } from './hooks/useAuth'
import Acorn from './pages/Acorn'
import Chat from './pages/Chat'
import ChatHistory from './pages/ChatHistory'
import CourseDetail from './pages/CourseDetail'
import Dashboard from './pages/Dashboard'
import DegreePlanner from './pages/DegreePlanner'
import DemoAcorn from './pages/demo/DemoAcorn'
import DemoChat from './pages/demo/DemoChat'
import DemoCourseDetail from './pages/demo/DemoCourseDetail'
import DemoDashboard from './pages/demo/DemoDashboard'
import DemoPlanner from './pages/demo/DemoPlanner'
import Disclaimers from './pages/Disclaimers'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import SignIn from './pages/SignIn'
import PrivacyPolicy from './pages/PrivacyPolicy'
import ResetPassword from './pages/ResetPassword'
import TermsOfUse from './pages/TermsOfUse'

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
  const { isAuthenticated, isReady } = useAuth()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!isReady || !isAuthenticated) return

    client.get('/api/courses/dashboard')
      .then(({ data }) => {
        queryClient.setQueryData(['dashboard'], data)
        ;(data.courses ?? []).forEach((course, index) => {
          setTimeout(() => {
            client.get(`/api/courses/${course.id}/grades`)
              .then(({ data: gradesData }) => {
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
      <Route path="/signin" element={isAuthenticated ? <Navigate to="/" replace /> : <SignIn />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />
      <Route path="/auth/reset-password" element={<ResetPassword />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfUse />} />
      <Route path="/disclaimers" element={<Disclaimers />} />
      <Route path="/demo" element={<Navigate to="/demo/dashboard" replace />} />
      <Route
        element={
          <DemoDataProvider>
            <DemoShell />
          </DemoDataProvider>
        }
      >
        <Route path="/demo/dashboard" element={<DemoDashboard />} />
        <Route path="/demo/courses/:courseId" element={<DemoCourseDetail />} />
        <Route path="/demo/chat" element={<DemoChat />} />
        <Route path="/demo/acorn" element={<DemoAcorn />} />
        <Route path="/demo/planner" element={<DemoPlanner />} />
      </Route>
      <Route
        path="/onboarding"
        element={
          <ProtectedRoute>
            <Onboarding />
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
        <Route path="/" element={<Dashboard />} />
        <Route path="/courses/:id" element={<CourseDetail />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/history" element={<ChatHistory />} />
        <Route path="/chat/:conversationId" element={<Chat />} />
        <Route path="/acorn" element={<Acorn />} />
        <Route path="/degree-planner" element={<DegreePlanner />} />
      </Route>
    </Routes>
  )
}
