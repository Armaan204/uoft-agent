import { useState, useEffect, useRef } from 'react'
import dashboardImg from '../assets/dashboard.png'
import chatImg from '../assets/chat.png'
import gradeImg from '../assets/gradebreakdown.png'
import acornImg from '../assets/acorn.png'

const googleAuthUrl = `${import.meta.env.VITE_API_URL || ''}/auth/google`
const GITHUB_URL = 'https://github.com/Armaan204/uoft-agent'

const INTERVAL = 5000

const slides = [
  { img: dashboardImg, label: 'Dashboard',       caption: 'All your courses, grades, and deadlines in one place' },
  { img: chatImg,      label: 'AI Assistant',    caption: 'Ask anything about your grades, courses, or assignments' },
  { img: gradeImg,     label: 'Grade Breakdown', caption: 'Weighted grade calculations and what-if scenarios' },
  { img: acornImg,     label: 'ACORN History',   caption: 'Import and explore your full academic transcript' },
]

export default function Login() {
  const [active, setActive] = useState(0)
  const intervalRef = useRef(null)
  const pausedRef = useRef(false)

  const startInterval = () => {
    clearInterval(intervalRef.current)
    intervalRef.current = setInterval(() => {
      if (!pausedRef.current) setActive(i => (i + 1) % slides.length)
    }, INTERVAL)
  }

  useEffect(() => {
    startInterval()
    return () => clearInterval(intervalRef.current)
  }, [])

  const goTo = (i) => { setActive(i); startInterval() }
  const prev = () => { setActive(i => (i - 1 + slides.length) % slides.length); startInterval() }
  const next = () => { setActive(i => (i + 1) % slides.length); startInterval() }

  return (
    <main
      className="login-screen login-screen--full"
      onMouseDown={() => { pausedRef.current = true }}
      onMouseUp={() => { pausedRef.current = false }}
      onMouseLeave={() => { pausedRef.current = false }}
      onTouchStart={() => { pausedRef.current = true }}
      onTouchEnd={() => { pausedRef.current = false }}
    >
      <div className="login-bg-slider" aria-hidden="true">
        {slides.map((slide, i) => (
          <div key={i} className={`login-bg-slide${i === active ? ' login-bg-slide--active' : ''}`}>
            <img src={slide.img} alt="" draggable={false} />
          </div>
        ))}
      </div>

      <div className="login-overlay" aria-hidden="true" />

      <nav className="login-nav">
        <div className="login-nav-brand">
          <svg viewBox="0 0 28 28" fill="none" aria-hidden="true" width="28" height="28">
            <path d="M14 6L3 11.5L14 17L25 11.5L14 6Z" fill="oklch(68% 0.16 240)" opacity="0.9" />
            <path d="M8 14.2V19.5C8 19.5 10.5 21.5 14 21.5C17.5 21.5 20 19.5 20 19.5V14.2L14 17L8 14.2Z" fill="oklch(68% 0.16 240)" opacity="0.55" />
            <circle cx="22.5" cy="8" r="1.1" fill="oklch(80% 0.12 200)" opacity="0.8" />
            <circle cx="20.5" cy="5.2" r="0.7" fill="oklch(75% 0.14 220)" opacity="0.6" />
            <circle cx="24.2" cy="6" r="0.6" fill="oklch(72% 0.14 260)" opacity="0.5" />
          </svg>
          <span>UofT Agent</span>
        </div>

        <div className="login-nav-actions">
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="btn-github">
            <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16" aria-hidden="true">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            <span className="btn-github-label">GitHub</span>
          </a>
          <button className="btn-google btn-google--nav" type="button" onClick={() => window.location.assign(googleAuthUrl)}>
            <svg className="g-logo" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4" />
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
              <path d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" fill="#FBBC05" />
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
            </svg>
            Sign in with Google
          </button>
        </div>
      </nav>

      <button
        className="login-arrow login-arrow--prev"
        onClick={prev}
        onMouseDown={e => e.stopPropagation()}
        aria-label="Previous slide"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      <button
        className="login-arrow login-arrow--next"
        onClick={next}
        onMouseDown={e => e.stopPropagation()}
        aria-label="Next slide"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20" aria-hidden="true">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      <div className="login-slide-footer">
        <div className="login-caption-stack">
          {slides.map((slide, i) => (
            <div key={i} className={`login-caption${i === active ? ' login-caption--active' : ''}`}>
              <span className="login-slide-label">{slide.label}</span>
              <p className="login-slide-text">{slide.caption}</p>
            </div>
          ))}
        </div>
        <div className="login-slide-dots">
          {slides.map((_, i) => (
            <button
              key={i}
              className={`login-slide-dot${i === active ? ' login-slide-dot--active' : ''}`}
              onClick={() => goTo(i)}
              onMouseDown={e => e.stopPropagation()}
              aria-label={`View ${slides[i].label}`}
            />
          ))}
        </div>
      </div>
    </main>
  )
}
