import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import client, { TOKEN_KEY } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const navigate = useNavigate()
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
        window.localStorage.setItem(TOKEN_KEY, nextToken)
        setToken(nextToken)
        const { data } = await client.get('/auth/me')
        setUser(data)
        navigate('/', { replace: true })
      },
      logout() {
        window.localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUser(null)
        navigate('/login', { replace: true })
      },
    }),
    [isReady, navigate, token, user],
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
