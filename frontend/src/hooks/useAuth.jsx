import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import client from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [user, setUser] = useState(null)
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const { data } = await client.get('/auth/me')
        if (!cancelled) {
          const prevUserId = sessionStorage.getItem('auth_user_id')
          if (prevUserId && prevUserId !== data.user_id) {
            queryClient.clear()
            window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
          }
          sessionStorage.setItem('auth_user_id', data.user_id)
          setUser(data)
        }
      } catch {
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setIsReady(true)
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isReady,
      async completeLogin() {
        queryClient.clear()
        const { data } = await client.get('/auth/me')
        setUser(data)
        navigate('/', { replace: true })
      },
      async logout() {
        try {
          await client.post('/auth/logout')
        } catch { /* best-effort */ }
        window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        queryClient.clear()
        setUser(null)
        navigate('/login', { replace: true })
      },
      async deleteAccount() {
        await client.delete('/auth/account')
        window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        queryClient.clear()
        setUser(null)
        navigate('/login', { replace: true })
      },
    }),
    [isReady, navigate, queryClient, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
