import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const THEME_KEY = 'uoft-agent-theme'
const ThemeContext = createContext(null)

function getSystemPreference() {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function getInitialTheme() {
  const saved = window.localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return getSystemPreference()
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    applyTheme(theme)
    window.localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    function handleChange() {
      if (!window.localStorage.getItem(THEME_KEY)) {
        setTheme(mq.matches ? 'light' : 'dark')
      }
    }
    mq.addEventListener('change', handleChange)
    return () => mq.removeEventListener('change', handleChange)
  }, [])

  const value = useMemo(
    () => ({
      theme,
      isDark: theme === 'dark',
      toggleTheme() {
        document.documentElement.setAttribute('data-theme-transitioning', '')
        setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
        setTimeout(() => {
          document.documentElement.removeAttribute('data-theme-transitioning')
        }, 350)
      },
    }),
    [theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
