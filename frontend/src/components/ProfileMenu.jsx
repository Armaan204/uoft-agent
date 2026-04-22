import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import client from '../api/client'

export default function ProfileMenu({ displayName, initials, onLogout, dropUp = false }) {
  const [open, setOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const menuRef = useRef(null)
  const queryClient = useQueryClient()

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

  async function disconnectQuercus() {
    if (disconnecting) return
    setDisconnecting(true)
    try {
      await client.delete('/api/courses/quercus-token')
      await queryClient.removeQueries({ queryKey: ['dashboard'] })
      await queryClient.removeQueries({ queryKey: ['courses'] })
      await queryClient.removeQueries({ queryKey: ['course-grades'] })
    } finally {
      setDisconnecting(false)
      setOpen(false)
    }
  }

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
          <button className="profile-dropdown-item" type="button" onClick={onLogout}>
            Log out
          </button>
          <button className="profile-dropdown-item" type="button" onClick={disconnectQuercus} disabled={disconnecting}>
            {disconnecting ? 'Disconnecting…' : 'Disconnect Quercus'}
          </button>
        </div>
      )}
    </div>
  )
}
