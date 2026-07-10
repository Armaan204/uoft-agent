import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'
import client from '../api/client'
import { useAuth } from '../hooks/useAuth'

const googleAuthUrl = '/auth/google'
const GITHUB_URL = 'https://github.com/Armaan204/uoft-agent'

export default function SignIn() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { completeLogin } = useAuth()
  const { isDark, toggleTheme } = useTheme()
  const [authMode, setAuthMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [authSubmitting, setAuthSubmitting] = useState(false)
  const emailConfirmed = searchParams.get('confirmed') === 'true'

  const resetAuthFeedback = () => {
    setAuthError('')
    setAuthMessage('')
  }

  const switchAuthMode = (mode) => {
    setAuthMode(mode)
    setPassword('')
    resetAuthFeedback()
  }

  const submitPasswordAuth = async (event) => {
    event.preventDefault()
    if (authSubmitting) return
    setAuthSubmitting(true)
    resetAuthFeedback()

    try {
      if (authMode === 'forgot') {
        const { data } = await client.post('/auth/password/forgot', { email })
        setAuthMessage(data?.message || 'If an account exists for that email, a reset link has been sent.')
        return
      }

      if (authMode === 'signup') {
        const { data } = await client.post('/auth/signup', { email, password })
        setAuthMessage(data?.message || 'Check your email to verify your account before signing in.')
        setPassword('')
        return
      }

      await client.post('/auth/login', { email, password })
      await completeLogin()
    } catch (error) {
      const detail = error?.response?.data?.detail
      setAuthError(typeof detail === 'string' ? detail : 'Unable to complete sign in. Try again.')
    } finally {
      setAuthSubmitting(false)
    }
  }

  return (
    <main className="signin-page">
      <nav className="login-nav">
        <div className="login-nav-brand">
          <svg viewBox="0 0 28 28" fill="none" aria-hidden="true" width="28" height="28">
            <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
            <path d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z" fill="oklch(68% 0.16 240)" opacity="0.55" />
            <circle cx="22.5" cy="8" r="1.1" fill="oklch(80% 0.12 200)" opacity="0.8" />
            <circle cx="20.5" cy="5.2" r="0.7" fill="oklch(75% 0.14 220)" opacity="0.6" />
            <circle cx="24.2" cy="6" r="0.6" fill="oklch(72% 0.14 260)" opacity="0.5" />
          </svg>
          <Link to="/login" className="login-nav-brand-link">UofT Agent</Link>
        </div>

        <div className="login-nav-actions">
          <button className="btn-theme-nav" type="button" onClick={toggleTheme} aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}>
            {isDark ? (
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" width="18" height="18" aria-hidden="true">
                <circle cx="10" cy="10" r="3.5" />
                <path d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1L4.7 4.7" strokeLinecap="round" />
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" width="18" height="18" aria-hidden="true">
                <path d="M16.5 12.8A7 7 0 0 1 7.2 3.5 7 7 0 1 0 16.5 12.8Z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="btn-github">
            <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16" aria-hidden="true">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            <span className="btn-github-label">GitHub</span>
          </a>
        </div>
      </nav>

      <section className="auth-page">
        <div className="auth-panel">
          {emailConfirmed && (
            <div className="auth-confirmed-banner">
              <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18" aria-hidden="true">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span>Email verified! You can now log in.</span>
              <button type="button" className="auth-confirmed-dismiss" onClick={() => setSearchParams({})} aria-label="Dismiss">
                <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" /></svg>
              </button>
            </div>
          )}
          <button className="btn-google auth-google-btn" type="button" onClick={() => window.location.assign(googleAuthUrl)}>
            <svg className="g-logo" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4" />
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
              <path d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" fill="#FBBC05" />
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
            </svg>
            <span className="btn-google-label">Continue with Google</span>
          </button>
          <div className="auth-divider">
            <span>or</span>
          </div>
          <form className="landing-auth-form" onSubmit={submitPasswordAuth}>
            {authMode !== 'forgot' && (
              <div className="landing-auth-tabs" role="tablist" aria-label="Authentication mode">
                <button className={authMode === 'login' ? 'active' : ''} type="button" onClick={() => switchAuthMode('login')}>Log in</button>
                <button className={authMode === 'signup' ? 'active' : ''} type="button" onClick={() => switchAuthMode('signup')}>Sign up</button>
              </div>
            )}
            <label className="landing-auth-label">
              Email
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            {authMode !== 'forgot' && (
              <label className="landing-auth-label">
                Password
                <input
                  type="password"
                  autoComplete={authMode === 'signup' ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={8}
                  required
                />
              </label>
            )}
            {authError && <p className="landing-auth-error">{authError}</p>}
            {authMessage && <p className="landing-auth-message">{authMessage}</p>}
            <button className="landing-auth-submit" type="submit" disabled={authSubmitting}>
              {authSubmitting
                ? 'Working...'
                : authMode === 'signup'
                  ? 'Create account'
                  : authMode === 'forgot'
                    ? 'Send reset link'
                    : 'Log in'}
            </button>
            {authMode === 'forgot' ? (
              <div className="landing-auth-row">
                <button type="button" onClick={() => switchAuthMode('login')}>Back to login</button>
              </div>
            ) : (
              <div className="landing-auth-row">
                <button type="button" onClick={() => switchAuthMode('forgot')}>Forgot password?</button>
              </div>
            )}
          </form>
        </div>
      </section>

      <footer className="landing-footer">
        <Link to="/privacy" className="site-footer-link">Privacy Policy</Link>
        <Link to="/terms" className="site-footer-link">Terms of Use</Link>
        <Link to="/disclaimers" className="site-footer-link">Disclaimers</Link>
      </footer>
    </main>
  )
}
