import { useEffect, useRef, useState } from 'react'

import { useTheme } from '../hooks/useTheme'

export default function ProfileMenu({ displayName, initials, onLogout, dropUp = false, showThemeToggle = false }) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)
  const { isDark, toggleTheme } = useTheme()

  useEffect(() => {
    function handlePointer(event) {
      if (!menuRef.current?.contains(event.target)) {
        setOpen(false)
      }
    }

    function handleEscape(event) {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointer)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handlePointer)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [])

  return (
    <div className="profile-menu" ref={menuRef}>
      <button
        className={`profile-trigger ${open ? 'open' : ''}`}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="user-name">{displayName}</span>
        <div className="avatar">{initials}</div>
      </button>

      {open && (
        <div className={`profile-dropdown ${dropUp ? 'drop-up' : ''}`}>
          {showThemeToggle && (
            <button className="profile-dropdown-item profile-theme-item" type="button" onClick={toggleTheme}>
              {isDark ? (
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <circle cx="10" cy="10" r="3.5" />
                  <path d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1L4.7 4.7" strokeLinecap="round" />
                </svg>
              ) : (
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <path d="M16.5 12.8A7 7 0 0 1 7.2 3.5 7 7 0 1 0 16.5 12.8Z" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              {isDark ? 'Light mode' : 'Dark mode'}
            </button>
          )}
          <button className="profile-dropdown-item" type="button" onClick={onLogout}>
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
