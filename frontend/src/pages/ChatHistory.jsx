import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { deleteConversation, fetchChatHistory } from '../api/chat'
import { useAuth } from '../hooks/useAuth'
import {
  buildWelcomeThread,
  formatHistoryTimestamp,
  getChatStorageKey,
  loadStoredThread,
  saveStoredThread,
} from '../utils/chatThread'

export default function ChatHistory() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const storageKey = useMemo(() => getChatStorageKey(user), [user])
  const [toast, setToast] = useState(false)
  const toastTimer = useRef(null)
  const activeThread = useMemo(() => {
    try {
      return loadStoredThread(storageKey)
    } catch {
      return buildWelcomeThread()
    }
  }, [storageKey])

  const historyQuery = useQuery({
    queryKey: ['chat-history'],
    queryFn: fetchChatHistory,
    enabled: Boolean(user),
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (deletedConversationId) => {
      queryClient.setQueryData(['chat-history'], (current) =>
        Array.isArray(current) ? current.filter((item) => item.id !== deletedConversationId) : current,
      )

      if (activeThread?.conversationId === deletedConversationId) {
        saveStoredThread(storageKey, buildWelcomeThread())
      }

      clearTimeout(toastTimer.current)
      setToast(true)
      toastTimer.current = setTimeout(() => setToast(false), 2500)
    },
  })

  function handleNewChat() {
    const nextThread = buildWelcomeThread()
    saveStoredThread(storageKey, nextThread)
    navigate('/chat')
  }

  function handleOpenConversation(conversationId) {
    navigate(`/chat/${conversationId}`)
  }

  function handleDeleteConversation(conversationId) {
    if (!conversationId || deleteMutation.isPending) return
    deleteMutation.mutate(conversationId)
  }

  return (
    <div className="chat-main chat-page">
      <div className="chat-header">
        <div className="chat-header-left">
          <div>
            <div className="chat-header-title">UofT Agent</div>
            <div className="chat-header-sub">Knows your courses, grades, and deadlines</div>
          </div>
        </div>
        <div className="chat-header-actions">
          <button className="chat-history-btn active" type="button" onClick={() => navigate('/chat')} aria-label="Back to chat">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <path d="M10 5.5v4.5l3 1.8" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M17 10a7 7 0 1 1-2.05-4.95" strokeLinecap="round" />
              <path d="M17 3v4h-4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button className="chat-secondary-btn" type="button" onClick={handleNewChat}>
            New chat
          </button>
        </div>
      </div>

      <div className="chat-history-route-body">
        <div className="chat-history-route-head">
          <div>
            <div className="chat-history-route-title">History</div>
            <div className="chat-history-route-copy">Resume a saved thread or remove one you no longer need.</div>
          </div>
        </div>

        {historyQuery.isLoading && (
          <div className="dashboard-loading-card" aria-live="polite">
            <div className="loading-spinner" aria-hidden="true" />
            <div className="dashboard-loading-copy">Loading history…</div>
          </div>
        )}

        {historyQuery.isError && !historyQuery.isLoading && (
          <div className="history-empty-state">Could not load history right now.</div>
        )}

        {!historyQuery.isLoading && !historyQuery.isError && historyQuery.data?.length === 0 && (
          <div className="history-empty-state">No saved conversations yet.</div>
        )}

        {!historyQuery.isLoading && !historyQuery.isError && historyQuery.data?.length > 0 && (
          <div className="history-list-page">
            {historyQuery.data.map((item) => {
              const isDeleting = deleteMutation.isPending && deleteMutation.variables === item.id
              const isActive = activeThread?.conversationId === item.id

              return (
                <div className={`history-list-row ${isActive ? 'active' : ''}`} key={item.id}>
                  <button
                    className="history-list-open"
                    type="button"
                    onClick={() => handleOpenConversation(item.id)}
                    disabled={isDeleting}
                  >
                    <span className="history-list-title">{item.title || 'Untitled chat'}</span>
                    <span className="history-list-meta">{formatHistoryTimestamp(item.last_message_at || item.updated_at)}</span>
                  </button>
                  <button
                    className="chat-history-delete"
                    type="button"
                    onClick={() => handleDeleteConversation(item.id)}
                    disabled={isDeleting}
                    aria-label={`Delete ${item.title || 'chat'}`}
                  >
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                      <path d="M3.5 4.5h9" strokeLinecap="round" />
                      <path d="M6.5 2.8h3" strokeLinecap="round" />
                      <path d="M5.2 4.5v7.1a1 1 0 0 0 1 1h3.6a1 1 0 0 0 1-1V4.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {deleteMutation.isPending && <div className="chat-delete-backdrop" aria-hidden="true" />}

      {toast && (
        <div className="chat-delete-toast" role="status" aria-live="polite">
          <svg className="chat-delete-toast-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="8" cy="8" r="6.5" strokeOpacity="0.4" />
            <path d="M5.5 8.2l1.8 1.8 3.2-3.2" />
          </svg>
          Chat deleted
        </div>
      )}
    </div>
  )
}
