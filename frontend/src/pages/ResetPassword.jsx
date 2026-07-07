import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import client from '../api/client'

function readRecoveryTokens() {
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const queryParams = new URLSearchParams(window.location.search)
  return {
    accessToken: hashParams.get('access_token') || queryParams.get('access_token') || '',
    refreshToken: hashParams.get('refresh_token') || queryParams.get('refresh_token') || '',
  }
}

export default function ResetPassword() {
  const navigate = useNavigate()
  const tokens = useMemo(() => readRecoveryTokens(), [])
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState(tokens.accessToken && tokens.refreshToken ? '' : 'This password reset link is missing required tokens.')
  const [submitting, setSubmitting] = useState(false)

  async function submitReset(event) {
    event.preventDefault()
    if (submitting) return
    setError('')
    setMessage('')

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      const { data } = await client.post('/auth/password/reset', {
        access_token: tokens.accessToken,
        refresh_token: tokens.refreshToken,
        password,
      })
      setMessage(data?.message || 'Password updated. You can now sign in.')
      setPassword('')
      setConfirmPassword('')
      setTimeout(() => navigate('/signin', { replace: true }), 1200)
    } catch (resetError) {
      setError(resetError?.response?.data?.detail || 'Unable to reset password. Request a new link and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <Link to="/signin" className="auth-brand">
          <svg viewBox="0 0 28 28" fill="none" aria-hidden="true" width="24" height="24">
            <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
            <path d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z" fill="oklch(68% 0.16 240)" opacity="0.55" />
          </svg>
          UofT Agent
        </Link>
        <h1>Reset password</h1>
        <form className="landing-auth-form auth-reset-form" onSubmit={submitReset}>
          <label className="landing-auth-label">
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              required
              disabled={!tokens.accessToken || !tokens.refreshToken}
            />
          </label>
          <label className="landing-auth-label">
            Confirm password
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={8}
              required
              disabled={!tokens.accessToken || !tokens.refreshToken}
            />
          </label>
          {error && <p className="landing-auth-error">{error}</p>}
          {message && <p className="landing-auth-message">{message}</p>}
          <button className="landing-auth-submit" type="submit" disabled={submitting || !tokens.accessToken || !tokens.refreshToken}>
            {submitting ? 'Updating...' : 'Update password'}
          </button>
        </form>
      </section>
    </main>
  )
}
