import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import client, { TOKEN_KEY } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [token, setToken] = useState(() => window.localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(null)
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      const savedToken = window.localStorage.getItem(TOKEN_KEY)
      if (!savedToken) {
        setUser(null)
        setToken(null)
        setIsReady(true)
        return
      }

      try {
        const { data } = await client.get('/auth/me')
        if (!cancelled) {
          setToken(savedToken)
          setUser(data)
        }
      } catch (_error) {
        if (!cancelled) {
          window.localStorage.removeItem(TOKEN_KEY)
          setToken(null)
          setUser(null)
        }
      } finally {
        if (!cancelled) {
          setIsReady(true)
        }
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(token),
      isReady,
      async completeLogin(nextToken) {
        queryClient.clear()
        window.localStorage.setItem(TOKEN_KEY, nextToken)
        setToken(nextToken)
        const { data } = await client.get('/auth/me')
        setUser(data)
        navigate('/', { replace: true })
      },
      logout() {
        window.localStorage.removeItem(TOKEN_KEY)
        window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        queryClient.clear()
        setToken(null)
        setUser(null)
        navigate('/login', { replace: true })
      },
      async deleteAccount() {
        await client.delete('/auth/account')
        window.localStorage.removeItem(TOKEN_KEY)
        window.localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
        queryClient.clear()
        setToken(null)
        setUser(null)
        navigate('/login', { replace: true })
      },
    }),
    [isReady, navigate, queryClient, token, user],
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
