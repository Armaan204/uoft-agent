import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import client from '../api/client'

export default function Onboarding() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const connectMutation = useMutation({
    mutationFn: async (quercusToken) => {
      await client.get('/api/courses', {
        params: { quercus_token: quercusToken },
      })
      await client.post('/api/courses/quercus-token', { token: quercusToken })
    },
    onSuccess: async () => {
      setErrorMessage('')
      await queryClient.invalidateQueries({ queryKey: ['quercus-token-status'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      navigate('/', { replace: true })
    },
    onError: () => {
      setErrorMessage('Invalid token, please try again')
    },
  })

  function handleSubmit(event) {
    event.preventDefault()
    const trimmed = token.trim()
    if (!trimmed) {
      setErrorMessage('Please enter a Quercus token')
      return
    }
    setErrorMessage('')
    connectMutation.mutate(trimmed)
  }

  return (
    <main className="login-screen onboarding-screen">
      <div className="login-card onboarding-card">
        <div className="icon-wrap">
          <svg viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
            <path
              d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z"
              fill="oklch(68% 0.16 240)"
              opacity="0.55"
            />
            <circle cx="22.5" cy="8" r="1.1" fill="oklch(80% 0.12 200)" opacity="0.8" />
            <circle cx="20.5" cy="5.2" r="0.7" fill="oklch(75% 0.14 220)" opacity="0.6" />
            <circle cx="24.2" cy="6" r="0.6" fill="oklch(72% 0.14 260)" opacity="0.5" />
          </svg>
        </div>

        <h1>Connect Quercus</h1>
        <p className="tagline onboarding-copy">Enter your Quercus personal access token to get started.</p>
        <p className="onboarding-help">
          Generate one at <strong>q.utoronto.ca</strong> → <strong>Account</strong> → <strong>Settings</strong> →{' '}
          <strong>New Access Token</strong>
        </p>
        <div className="divider" />

        <form className="onboarding-form" onSubmit={handleSubmit}>
          <label className="onboarding-label" htmlFor="quercus-token">
            Quercus access token
          </label>
          <input
            id="quercus-token"
            className="onboarding-input"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Paste your personal access token"
            autoComplete="off"
          />
          {errorMessage ? <div className="onboarding-error">{errorMessage}</div> : null}
          <button className="btn-google onboarding-submit" type="submit" disabled={connectMutation.isPending}>
            {connectMutation.isPending ? 'Connecting…' : 'Connect'}
          </button>
        </form>
      </div>
    </main>
  )
}
