import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import client from '../api/client'
import Logo from '../components/Logo'
import MarkdownMessage from '../components/MarkdownMessage'
import ToolCallBlock from '../components/ToolCallBlock'
import { useAuth } from '../hooks/useAuth'
import { getInitials } from '../utils/initials'

const DASHBOARD_STALE_TIME_MS = 5 * 60 * 1000
const DASHBOARD_GC_TIME_MS = 30 * 60 * 1000
const WELCOME_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  text: 'Hi. I have access to your courses, grades, and deadlines. Ask about finals, projections, or upcoming work.',
  toolCalls: [],
}

async function fetchDashboard() {
  const response = await client.get('/api/courses/dashboard')
  return response.data
}

export default function Chat() {
  const { user } = useAuth()
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState([WELCOME_MESSAGE])
  const [isHydrated, setIsHydrated] = useState(false)
  const scrollRef = useRef(null)
  const userInitials = getInitials(user?.name || user?.email)
  const storageKey = useMemo(() => {
    const userKey = String(user?.email || user?.id || 'anonymous').trim().toLowerCase()
    return `uoft-agent-chat:${userKey}`
  }, [user?.email, user?.id])

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
    mutationFn: async (message) => {
      const response = await client.post('/api/chat', { message })
      return response.data
    },
    onSuccess: (data) => {
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

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, mutation.isPending])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey)
      if (!raw) {
        setMessages([WELCOME_MESSAGE])
        setDraft('')
        setIsHydrated(true)
        return
      }

      const saved = JSON.parse(raw)
      const nextMessages = Array.isArray(saved?.messages) && saved.messages.length ? saved.messages : [WELCOME_MESSAGE]
      setMessages(nextMessages)
      setDraft(typeof saved?.draft === 'string' ? saved.draft : '')
    } catch {
      setMessages([WELCOME_MESSAGE])
      setDraft('')
    } finally {
      setIsHydrated(true)
    }
  }, [storageKey])

  useEffect(() => {
    if (!isHydrated) return

    window.localStorage.setItem(
      storageKey,
      JSON.stringify({
        messages,
        draft,
      }),
    )
  }, [draft, isHydrated, messages, storageKey])

  function sendMessage(text = draft) {
    const trimmed = text.trim()
    if (!trimmed || mutation.isPending) return

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
    mutation.mutate(trimmed)
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
        </div>

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

            {mutation.isPending && (
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
          <div className="chips">
            {suggestions.map((item) => (
              <button className="chip" key={item} type="button" onClick={() => setDraft(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="input-row">
            <textarea
              className="input-box"
              rows="1"
              placeholder="Ask about your grades, exams, deadlines…"
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
