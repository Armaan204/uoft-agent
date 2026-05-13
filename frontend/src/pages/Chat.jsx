import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import client from '../api/client'
import { fetchConversation, sendChatMessage } from '../api/chat'
import Logo from '../components/Logo'
import MarkdownMessage from '../components/MarkdownMessage'
import ToolCallBlock from '../components/ToolCallBlock'
import { useAuth } from '../hooks/useAuth'
import {
  buildWelcomeThread,
  getChatStorageKey,
  loadStoredThread,
  normalizeMessages,
  saveStoredThread,
  WELCOME_MESSAGE,
} from '../utils/chatThread'
import { getInitials } from '../utils/initials'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000
const DASHBOARD_GC_TIME_MS = 30 * 60 * 1000

async function fetchDashboard() {
  const response = await client.get('/api/courses/dashboard')
  return response.data
}

export default function Chat() {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const { conversationId: routeConversationId } = useParams()
  const [draft, setDraft] = useState(location.state?.initialMessage || '')
  const [messages, setMessages] = useState([WELCOME_MESSAGE])
  const [conversationId, setConversationId] = useState(null)
  const [isHydrated, setIsHydrated] = useState(false)
  const [isMobileComposer, setIsMobileComposer] = useState(() => window.innerWidth < 768)
  const scrollRef = useRef(null)
  const queryClient = useQueryClient()
  const userInitials = getInitials(user?.name || user?.email)
  const storageKey = useMemo(() => getChatStorageKey(user), [user])

  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    staleTime: DASHBOARD_STALE_TIME_MS,
    gcTime: DASHBOARD_GC_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const suggestions = useMemo(() => {
    const items = [
      "What's my GPA this semester?",
      'Show upcoming deadlines',
      'Compare my courses by grade',
    ]

    const courses = dashboardQuery.data?.courses ?? []
    const lowestCourse = courses.reduce((lowest, course) => {
      const grade = typeof course.display_grade === 'number' ? course.display_grade : course.current_grade
      if (typeof grade !== 'number') return lowest
      if (!lowest || grade < lowest.grade) {
        return { courseCode: course.course_code, grade }
      }
      return lowest
    }, null)

    if (lowestCourse?.courseCode) {
      items.splice(2, 0, `How to improve ${String(lowestCourse.courseCode).slice(0, 6)}?`)
    }

    return items
  }, [dashboardQuery.data?.courses])

  const mutation = useMutation({
    mutationFn: ({ message, conversationId: activeConversationId }) => sendChatMessage(message, activeConversationId),
    onSuccess: (data, variables) => {
      if (data?.conversation_id && data.conversation_id !== variables?.conversationId) {
        setConversationId(data.conversation_id)
      }

      queryClient.invalidateQueries({ queryKey: ['chat-history'] })

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: data.answer,
          toolCalls: data.tool_calls ?? [],
        },
      ])
    },
  })

  const loadConversationMutation = useMutation({
    mutationFn: fetchConversation,
    onSuccess: (data) => {
      const nextThread = {
        conversationId: data.id,
        draft: '',
        messages: normalizeMessages(data.messages),
        updatedAt: new Date().toISOString(),
      }

      setConversationId(nextThread.conversationId)
      setMessages(nextThread.messages)
      setDraft('')
      saveStoredThread(storageKey, nextThread)
    },
    onError: () => {
      navigate('/chat/history', { replace: true })
    },
  })

  useEffect(() => {
    function handleResize() {
      setIsMobileComposer(window.innerWidth < 768)
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, mutation.isPending])

  useEffect(() => {
    const initialMessage = location.state?.initialMessage

    try {
      const saved = loadStoredThread(storageKey)
      setConversationId(saved.conversationId)
      setMessages(saved.messages)
      
      if (initialMessage) {
        saved.draft = initialMessage
        setDraft(initialMessage)
        navigate(location.pathname, { replace: true, state: {} })
      } else {
        setDraft(saved.draft)
      }
      
      saveStoredThread(storageKey, saved)
    } catch {
      const fallback = buildWelcomeThread()
      setConversationId(fallback.conversationId)
      setMessages(fallback.messages)
      
      if (initialMessage) {
        fallback.draft = initialMessage
        setDraft(initialMessage)
        navigate(location.pathname, { replace: true, state: {} })
      } else {
        setDraft(fallback.draft)
      }
      
      saveStoredThread(storageKey, fallback)
    } finally {
      setIsHydrated(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey])

  useEffect(() => {
    if (!isHydrated || !conversationId) return

    saveStoredThread(storageKey, {
      conversationId,
      messages,
      draft,
      updatedAt: new Date().toISOString(),
    })
  }, [conversationId, draft, isHydrated, messages, storageKey])

  useEffect(() => {
    if (!isHydrated || !routeConversationId) return
    if (routeConversationId === conversationId) return
    if (loadConversationMutation.isPending && loadConversationMutation.variables === routeConversationId) return

    loadConversationMutation.mutate(routeConversationId)
  }, [conversationId, isHydrated, loadConversationMutation, routeConversationId])

  function resetConversation() {
    if (mutation.isPending || loadConversationMutation.isPending) return

    const nextThread = buildWelcomeThread()
    setConversationId(nextThread.conversationId)
    setMessages(nextThread.messages)
    setDraft(nextThread.draft)
    saveStoredThread(storageKey, nextThread)
    navigate('/chat')
  }

  function sendMessage(text = draft) {
    const trimmed = text.trim()
    if (!trimmed || mutation.isPending || !conversationId) return

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: 'user',
        text: trimmed,
        toolCalls: [],
      },
    ])
    setDraft('')
    mutation.mutate({ message: trimmed, conversationId })
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
          <button className="chat-history-btn" type="button" onClick={() => navigate('/chat/history')} aria-label="Open chat history">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <path d="M10 5.5v4.5l3 1.8" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M17 10a7 7 0 1 1-2.05-4.95" strokeLinecap="round" />
              <path d="M17 3v4h-4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button
            className="chat-secondary-btn"
            type="button"
            onClick={resetConversation}
            disabled={mutation.isPending || loadConversationMutation.isPending}
          >
            New chat
          </button>
        </div>
      </div>

      {loadConversationMutation.isError && (
        <div className="chat-status-banner">Could not load that conversation.</div>
      )}

      <div className="messages-scroll" ref={scrollRef}>
        <div className="messages-inner">
          {messages.map((message) => (
            <div className={`msg-row ${message.role === 'user' ? 'user' : 'ai'}`} key={message.id}>
              <div className={`msg-avatar ${message.role === 'user' ? 'user' : 'ai'}`}>
                {message.role === 'user' ? userInitials : <Logo compact />}
              </div>
              <div className="msg-bubble-wrap">
                {message.toolCalls.length > 0 && (
                  <div className="tool-stack">
                    {message.toolCalls.map((toolCall, index) => (
                      <ToolCallBlock key={`${message.id}-${index}`} toolCall={toolCall} />
                    ))}
                  </div>
                )}
                <div className={`msg-bubble ${message.role === 'user' ? 'user' : 'ai'}`}>
                  {message.role === 'assistant' ? <MarkdownMessage text={message.text} /> : message.text}
                </div>
              </div>
            </div>
          ))}

          {(mutation.isPending || loadConversationMutation.isPending) && (
            <div className="msg-row ai">
              <div className="msg-avatar ai"><Logo compact /></div>
              <div className="msg-bubble ai typing-bubble">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="input-area">
        {!isMobileComposer && (
          <div className="chips">
            {suggestions.map((item) => (
              <button className="chip" key={item} type="button" onClick={() => setDraft(item)}>
                {item}
              </button>
            ))}
          </div>
        )}
        <div className="input-row">
          <textarea
            className="input-box"
            rows="1"
            placeholder={isMobileComposer ? '' : 'Ask about your grades, exams, deadlines…'}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                sendMessage()
              }
            }}
          />
          <button className="send-btn" type="button" onClick={() => sendMessage()}>
            <svg viewBox="0 0 16 16" fill="none" stroke="white" strokeWidth="1.8">
              <path d="M13 8H3M9 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
