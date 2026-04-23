import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import client from '../api/client'
import MarkdownMessage from '../components/MarkdownMessage'
import ToolCallBlock from '../components/ToolCallBlock'
import { useAuth } from '../hooks/useAuth'
import { getInitials } from '../utils/initials'

const suggestions = [
  "What's my GPA this semester?",
  'Show upcoming deadlines',
  'How to improve MATB44?',
  'Compare my courses by grade',
]

export default function Chat() {
  const { user } = useAuth()
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Hi. I have access to your courses, grades, and deadlines. Ask about finals, projections, or upcoming work.',
      toolCalls: [],
    },
  ])
  const scrollRef = useRef(null)
  const userInitials = getInitials(user?.name || user?.email)

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
                  {message.role === 'user' ? userInitials : 'AI'}
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
                <div className="msg-avatar ai">AI</div>
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
