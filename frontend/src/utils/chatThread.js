export const WELCOME_MESSAGE = {
  id: 'welcome',
  role: 'assistant',
  text: 'Hi. I have access to your courses, grades, and deadlines. Ask about finals, projections, or upcoming work.',
  toolCalls: [],
}

export function getChatStorageKey(user) {
  const userKey = String(user?.email || user?.id || 'anonymous').trim().toLowerCase()
  return `uoft-agent-chat:${userKey}`
}

export function buildWelcomeThread() {
  return {
    conversationId: crypto.randomUUID(),
    draft: '',
    messages: [WELCOME_MESSAGE],
    updatedAt: new Date().toISOString(),
  }
}

export function normalizeMessages(value) {
  if (!Array.isArray(value) || !value.length) {
    return [WELCOME_MESSAGE]
  }

  const normalized = value
    .map((message, index) => {
      if (!message || typeof message !== 'object') return null

      const role = message.role === 'user' ? 'user' : 'assistant'
      const text = typeof message.text === 'string' ? message.text : ''
      if (!text.trim()) return null

      return {
        id: typeof message.id === 'string' && message.id.trim() ? message.id : `restored-${index}`,
        role,
        text,
        toolCalls: Array.isArray(message.toolCalls) ? message.toolCalls : [],
      }
    })
    .filter(Boolean)

  return normalized.length ? normalized : [WELCOME_MESSAGE]
}

export function parseStoredThread(raw) {
  if (!raw) return null

  const parsed = JSON.parse(raw)
  return {
    conversationId:
      typeof parsed?.conversationId === 'string' && parsed.conversationId.trim()
        ? parsed.conversationId
        : crypto.randomUUID(),
    draft: typeof parsed?.draft === 'string' ? parsed.draft : '',
    messages: normalizeMessages(parsed?.messages),
    updatedAt: typeof parsed?.updatedAt === 'string' ? parsed.updatedAt : new Date().toISOString(),
  }
}

export function loadStoredThread(storageKey) {
  return (
    parseStoredThread(window.sessionStorage.getItem(storageKey)) ??
    parseStoredThread(window.localStorage.getItem(storageKey)) ??
    buildWelcomeThread()
  )
}

export function saveStoredThread(storageKey, thread) {
  window.sessionStorage.setItem(storageKey, JSON.stringify(thread))
  window.localStorage.removeItem(storageKey)
}

export function formatHistoryTimestamp(value) {
  if (!value) return ''

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed)
}
