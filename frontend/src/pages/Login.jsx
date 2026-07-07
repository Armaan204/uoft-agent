import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'
import dashboardDark from '../assets/dashboard_dark.png'
import dashboardLight from '../assets/dashboard_light.png'
import chatDark from '../assets/chat_dark.png'
import chatLight from '../assets/chat_light.png'
import gradeDark from '../assets/gradebreakdown_dark.png'
import gradeLight from '../assets/gradebreakdown_light.png'
import acornDark from '../assets/acorn_dark.png'
import acornLight from '../assets/acorn_light.png'

const GITHUB_URL = 'https://github.com/Armaan204/uoft-agent'

const features = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </svg>
    ),
    title: 'Live Grades',
    description: 'Weighted grades pulled directly from Quercus, updated automatically every time you open the app.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    title: 'AI Assistant',
    description: 'Ask about your deadlines, simulate what-if grade scenarios, or get a quick semester summary.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
      </svg>
    ),
    title: 'Degree Planner',
    description: 'Import your ACORN transcript and track graduation progress against your program requirements.',
  },
]

export default function Login() {
  const navigate = useNavigate()
  const { isDark, toggleTheme } = useTheme()
  const [activeTab, setActiveTab] = useState(0)

  const showcase = [
    { img: isDark ? dashboardDark : dashboardLight, label: 'Dashboard' },
    { img: isDark ? chatDark : chatLight, label: 'AI Chat' },
    { img: isDark ? gradeDark : gradeLight, label: 'Grade Breakdown' },
    { img: isDark ? acornDark : acornLight, label: 'ACORN Import' },
  ]
  const [lightboxImage, setLightboxImage] = useState(null)

  const openLightbox = (item) => {
    setLightboxImage(item)
  }

  const closeLightbox = () => {
    setLightboxImage(null)
  }

  useEffect(() => {
    if (!lightboxImage) return undefined

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        closeLightbox()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [lightboxImage])

  return (
    <main className="landing">
      {/* ── Nav ──────────────────────────────────────────── */}
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
          <button className="btn-signin-nav" type="button" onClick={() => navigate('/signin')}>
            Sign in
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────── */}
      <section className="landing-hero">
        <div className="landing-hero-content">
          <div className="landing-badge">
            <svg viewBox="0 0 16 16" fill="none" width="14" height="14" aria-hidden="true">
              <path d="M8 1l2.35 4.76 5.25.77-3.8 3.7.9 5.23L8 13.27l-4.7 2.19.9-5.23-3.8-3.7 5.25-.77L8 1z" fill="oklch(78% 0.15 85)" />
            </svg>
            Free &amp; open source
          </div>
          <h1 className="landing-headline">
            Know exactly where<br className="landing-br" />{' '}you stand in every course
          </h1>
          <p className="landing-sub">
            UofT Agent connects to Quercus and calculates your real weighted grades,
            upcoming deadlines, and what-if scenarios — so you never have to guess again.
          </p>
          <div className="landing-hero-buttons">
            <button className="btn-signin-hero" type="button" onClick={() => navigate('/signin')}>
              Get started
            </button>
            <button className="btn-demo landing-cta-secondary" type="button" onClick={() => navigate('/demo')}>
              Try the demo
            </button>
          </div>
        </div>
        <div className="landing-hero-image">
          <button
            className="landing-image-button"
            type="button"
            onClick={() => openLightbox({
              img: isDark ? dashboardDark : dashboardLight,
              label: 'Dashboard',
              alt: 'UofT Agent dashboard showing course grades and deadlines',
            })}
            aria-label="Enlarge dashboard screenshot"
          >
            <img key={isDark ? 'hero-dark' : 'hero-light'} src={isDark ? dashboardDark : dashboardLight} alt="UofT Agent dashboard showing course grades and deadlines" draggable={false} />
          </button>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────── */}
      <section className="landing-features">
        <h2 className="landing-section-title">Everything you need, nothing you don't</h2>
        <div className="landing-features-grid">
          {features.map((feature) => (
            <div className="landing-feature-card" key={feature.title}>
              <div className="landing-feature-icon">{feature.icon}</div>
              <h3 className="landing-feature-title">{feature.title}</h3>
              <p className="landing-feature-desc">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Showcase ─────────────────────────────────────── */}
      <section className="landing-showcase">
        <h2 className="landing-section-title">See it in action</h2>
        <div className="landing-showcase-tabs">
          {showcase.map((item, i) => (
            <button
              className={`landing-tab${i === activeTab ? ' landing-tab--active' : ''}`}
              key={item.label}
              type="button"
              onClick={() => setActiveTab(i)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="landing-showcase-frame">
          {showcase.map((item, i) => (
            <button
              key={`${item.label}-${isDark ? 'dark' : 'light'}`}
              className={`landing-showcase-img${i === activeTab ? ' landing-showcase-img--active' : ''}`}
              type="button"
              onClick={() => openLightbox({ ...item, alt: `${item.label} screenshot` })}
              aria-label={`Enlarge ${item.label} screenshot`}
            >
              <img
                src={item.img}
                alt={item.label}
                draggable={false}
              />
            </button>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ───────────────────────────────────── */}
      <section className="landing-bottom-cta">
        <h2 className="landing-cta-headline">Ready to take control of your grades?</h2>
        <p className="landing-cta-sub">Set up takes 30 seconds. Create an account, then connect Quercus when you are ready.</p>
        <button className="btn-signin-hero landing-cta" type="button" onClick={() => navigate('/signin')}>
          Get started
        </button>
        <p className="landing-origin">
          Built by a UTSC student. Open source on{' '}
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">GitHub</a>.
        </p>
      </section>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className="landing-footer">
        <Link to="/privacy" className="site-footer-link">Privacy Policy</Link>
        <Link to="/terms" className="site-footer-link">Terms of Use</Link>
        <Link to="/disclaimers" className="site-footer-link">Disclaimers</Link>
      </footer>

      {lightboxImage && (
        <div
          className="landing-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={`${lightboxImage.label} enlarged screenshot`}
          onClick={closeLightbox}
        >
          <button
            className="landing-lightbox-close"
            type="button"
            onClick={closeLightbox}
            aria-label="Close enlarged image"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
          <figure className="landing-lightbox-figure" onClick={(event) => event.stopPropagation()}>
            <img src={lightboxImage.img} alt={lightboxImage.alt} draggable={false} />
            <figcaption>{lightboxImage.label}</figcaption>
          </figure>
        </div>
      )}
    </main>
  )
}
