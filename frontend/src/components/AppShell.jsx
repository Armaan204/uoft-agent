import { NavLink, Outlet } from 'react-router-dom'

import Logo from './Logo'
import ProfileMenu from './ProfileMenu'
import { useAuth } from '../hooks/useAuth'
import { getInitials } from '../utils/initials'

export default function AppShell() {
  const { user, logout } = useAuth()
  const displayName = user?.name || user?.email || 'You'
  const initials = getInitials(displayName)

  return (
    <div className="app-shell">
      <header className="mobile-topbar">
        <div className="mobile-topbar-brand">
          <Logo />
        </div>
        <ProfileMenu displayName={displayName} initials={initials} onLogout={logout} />
      </header>

      <aside className="sidebar app-sidebar">
        <div className="sidebar-logo">
          <Logo />
        </div>

        <nav className="sidebar-nav">
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/" end>
            Dashboard
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/chat">
            Chat
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/acorn">
            ACORN
          </NavLink>
          <NavLink className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`} to="/degree-planner">
            Degree Planner
          </NavLink>
        </nav>

        <div className="sidebar-bottom">
          <a
            href="https://forms.gle/XjeMfbbynAMnpvye7"
            target="_blank"
            rel="noopener noreferrer"
            className="sidebar-item sidebar-feedback"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            Give Feedback
          </a>
          <ProfileMenu displayName={displayName} initials={initials} onLogout={logout} dropUp />
        </div>
      </aside>

      <main className="app-content">
        <Outlet />
      </main>

      <nav className="mobile-bottom-nav" aria-label="Primary navigation">
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/" end>
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M3 8.5 10 3l7 5.5V17H3V8.5Z" strokeLinejoin="round" />
            <path d="M7.5 17v-4.5h5V17" strokeLinejoin="round" />
          </svg>
          <span>Dashboard</span>
        </NavLink>
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/chat">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M4 5.5h12v8H8l-4 3v-11Z" strokeLinejoin="round" />
          </svg>
          <span>Chat</span>
        </NavLink>
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/acorn">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M4 4h12v12H4z" />
            <path d="M7 11.5 9 9.5l2 2 2.5-3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>ACORN</span>
        </NavLink>
        <NavLink className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`} to="/degree-planner">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path d="M3 5h14M3 10h9M3 15h6" strokeLinecap="round" />
            <circle cx="15.5" cy="13.5" r="3" />
            <path d="M15.5 12v1.5l1 1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Planner</span>
        </NavLink>
      </nav>
    </div>
  )
}
