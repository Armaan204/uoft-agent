import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'

import client from '../api/client'
import tutorialAccount from '../assets/tutorial_clickaccount.png'
import tutorialSettings from '../assets/tutorial_clicksettings.png'
import tutorialNewToken from '../assets/tutorial_clicknewaccesstoken.png'
import tutorialFill from '../assets/tutorial_filltokendetails.png'

const TUTORIAL_STEPS = [
  { img: tutorialAccount, label: 'Click "Account" in the left sidebar' },
  { img: tutorialSettings, label: 'Click "Settings"' },
  { img: tutorialNewToken, label: 'Scroll down and click "+ New Access Token"' },
  { img: tutorialFill, label: 'Enter a purpose (e.g. "uoft-agent"), set an expiry date, and click "Generate Token"' },
]

function TokenTutorial() {
  const [open, setOpen] = useState(false)
  const [zoomedImg, setZoomedImg] = useState(null)

  return (
    <>
      <button
        type="button"
        className="token-tutorial-toggle"
        onClick={() => setOpen(true)}
      >
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor"
          strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <rect x="2" y="1.5" width="12" height="13" rx="1.5" />
          <path d="M5 5h6M5 8h6M5 11h3" />
        </svg>
        Show me how
      </button>

      {open && createPortal(
        <div className="token-tutorial-overlay" onClick={() => setOpen(false)}>
          <div className="token-tutorial-modal" onClick={e => e.stopPropagation()}>
            <div className="token-tutorial-modal-header">
              <h2 className="token-tutorial-modal-title">How to generate a Quercus token</h2>
              <button
                type="button"
                className="token-tutorial-close"
                onClick={() => setOpen(false)}
                aria-label="Close tutorial"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" aria-hidden>
                  <path d="M5 5l10 10M15 5 5 15" />
                </svg>
              </button>
            </div>

            <p className="token-tutorial-note">
              <span className="token-tutorial-do">Use a web browser to log into Quercus.</span>
              <span className="token-tutorial-dont">Do not use the Canvas app.</span>
            </p>

            <ol className="token-tutorial-steps">
              {TUTORIAL_STEPS.map((step, i) => (
                <li key={i} className="token-tutorial-step">
                  <div className="token-tutorial-step-header">
                    <span className="token-tutorial-number">{i + 1}</span>
                    <p className="token-tutorial-label">{step.label}</p>
                  </div>
                  <img
                    src={step.img}
                    alt={`Step ${i + 1}: ${step.label}`}
                    className={`token-tutorial-img token-tutorial-img--${i + 1}`}
                    onClick={() => setZoomedImg(step.img)}
                  />
                  {i === 3 && (
                    <div className="token-tutorial-step-header" style={{ marginTop: 8 }}>
                      <span className="token-tutorial-number">5</span>
                      <p className="token-tutorial-label">Copy the generated token and paste it into the field on the previous page</p>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </div>

          {zoomedImg && (
            <div className="token-tutorial-lightbox" onClick={e => { e.stopPropagation(); setZoomedImg(null) }}>
              <img src={zoomedImg} alt="Enlarged view" className="token-tutorial-lightbox-img" />
            </div>
          )}
        </div>,
        document.body
      )}
    </>
  )
}

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

        <h1 className="login-title">Connect Quercus</h1>
        <p className="tagline onboarding-copy">Enter your Quercus personal access token to get started.</p>
        <p className="onboarding-help">
          Generate one at{' '}
          <a href="https://q.utoronto.ca" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
            q.utoronto.ca
          </a>{' '}
          → <strong>Account</strong> → <strong>Settings</strong> → <strong>New Access Token</strong>
        </p>
        <TokenTutorial />
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
          <p className="onboarding-readonly-note">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
              <rect x="3" y="7" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
              <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            Your token is only used for read-only access. We never modify your Quercus data.
          </p>
          {errorMessage ? <div className="onboarding-error">{errorMessage}</div> : null}
          <button className="btn-google onboarding-submit" type="submit" disabled={connectMutation.isPending}>
            {connectMutation.isPending ? 'Connecting…' : 'Connect'}
          </button>
        </form>
      </div>

      <footer className="login-footer">
        <Link to="/privacy" className="site-footer-link">Privacy Policy</Link>
        <Link to="/terms" className="site-footer-link">Terms of Use</Link>
        <Link to="/disclaimers" className="site-footer-link">Disclaimers</Link>
      </footer>
    </main>
  )
}
