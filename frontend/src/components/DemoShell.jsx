import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import Logo from './Logo'

export default function DemoShell() {
  const navigate = useNavigate()

  return (
    <div className="app-shell">
      <header className="mobile-topbar">
        <div className="mobile-topbar-brand">
          <Logo />
        </div>
      </header>

      <aside className="sidebar app-sidebar">
        <div className="sidebar-logo">
          <Logo />
        </div>

        <nav className="sidebar-nav">
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/demo/dashboard" end>
            Dashboard
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/demo/chat">
            Chat
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/demo/acorn">
            ACORN
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/demo/planner">
            Degree Planner
          </NavLink>
        </nav>

        <div className="sidebar-bottom">
          <button className="btn-google demo-sidebar-cta" type="button" onClick={() => navigate('/login')}>
            Sign in with Google
          </button>
        </div>
      </aside>

      <main className="app-content">
        <div className="demo-banner">
          <span className="demo-banner-text">
            You're exploring a demo with sample data. Sign in to see your real grades.
          </span>
          <button className="demo-banner-btn" type="button" onClick={() => navigate('/login')}>
            Sign in with Google
          </button>
        </div>
        <Outlet />
      </main>

      <nav className="mobile-bottom-nav" aria-label="Primary navigation">
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/demo/dashboard" end>
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M3 8.5 10 3l7 5.5V17H3V8.5Z" strokeLinejoin="round" />
            <path d="M7.5 17v-4.5h5V17" strokeLinejoin="round" />
          </svg>
          <span>Dashboard</span>
        </NavLink>
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/demo/chat">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M4 5.5h12v8H8l-4 3v-11Z" strokeLinejoin="round" />
          </svg>
          <span>Chat</span>
        </NavLink>
      </nav>
    </div>
  )
}
