import { useState } from 'react'

import { useDemoData } from '../../context/DemoDataContext'
import Logo from '../../components/Logo'
import MarkdownMessage from '../../components/MarkdownMessage'

const googleAuthUrl = `${import.meta.env.VITE_API_URL || ''}/auth/google`

const WELCOME_TEXT = "Hi! I'm UofT Agent — your personal academic assistant. I can help you track grades, plan for exams, and monitor deadlines. Try one of the suggestions below to see how I work."

const SUGGESTIONS = [
  "What's my current GPA?",
  "What do I need on my CSCA08 final?",
  "When is my next deadline?",
  "Am I on track to graduate?",
]

export default function DemoChat() {
  const { chatResponses } = useDemoData()
  const [activeChip, setActiveChip] = useState(null)
  const startGoogleAuth = () => window.location.assign(googleAuthUrl)

  function handleChipClick(suggestion) {
    setActiveChip(suggestion)
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

      <div className="messages-scroll">
        <div className="messages-inner">
          <div className="msg-row ai">
            <div className="msg-avatar ai"><Logo compact /></div>
            <div className="msg-bubble-wrap">
              <div className="msg-bubble ai">{WELCOME_TEXT}</div>
            </div>
          </div>

          {activeChip && (
            <>
              <div className="msg-row user">
                <div className="msg-avatar user">DM</div>
                <div className="msg-bubble-wrap">
                  <div className="msg-bubble user">{activeChip}</div>
                </div>
              </div>
              <div className="msg-row ai">
                <div className="msg-avatar ai"><Logo compact /></div>
                <div className="msg-bubble-wrap">
                  <div className="msg-bubble ai">
                    <MarkdownMessage text={chatResponses[activeChip]} />
                  </div>
                </div>
              </div>
              <div className="msg-row ai">
                <div className="msg-avatar ai"><Logo compact /></div>
                <div className="msg-bubble-wrap">
                  <div className="msg-bubble ai demo-cta-bubble demo-chat-locked">
                    <p>Sign in to ask your own questions about your real grades and courses.</p>
                    <button className="btn-google demo-chat-signin" type="button" onClick={startGoogleAuth}>
                      Sign in with Google
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="input-area">
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button className="chip" key={s} type="button" onClick={() => handleChipClick(s)}>
              {s}
            </button>
          ))}
        </div>
        <div className="input-row demo-chat-locked">
          <textarea
            className="input-box"
            rows="1"
            placeholder="Sign in to chat with your personal AI assistant"
            disabled
          />
          <button className="send-btn" type="button" disabled>
            <svg viewBox="0 0 16 16" fill="none" stroke="white" strokeWidth="1.8">
              <path d="M13 8H3M9 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
