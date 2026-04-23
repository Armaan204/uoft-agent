import { NavLink, Outlet } from 'react-router-dom'

import Logo from './Logo'
import ProfileMenu from './ProfileMenu'
import { useAuth } from '../hooks/useAuth'
import { getInitials } from '../utils/initials'

export default function AppShell() {
  const { user, logout } = useAuth()
  const displayName = user?.name || user?.email || 'You'

  return (
    <div className="app-shell">
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
        </nav>

        <div className="sidebar-bottom">
          <ProfileMenu displayName={displayName} initials={getInitials(displayName)} onLogout={logout} dropUp />
        </div>
      </aside>

      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
