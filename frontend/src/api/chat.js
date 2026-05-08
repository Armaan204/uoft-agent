import client from './client'

export async function sendChatMessage(message, conversationId) {
  const response = await client.post('/api/chat', {
    message,
    conversation_id: conversationId,
  })
  return response.data
}

export async function fetchChatHistory() {
  const response = await client.get('/api/chat/history')
  return response.data?.conversations ?? []
}

export async function fetchConversation(conversationId) {
  const response = await client.get(`/api/chat/history/${conversationId}`)
  return response.data
}

export async function deleteConversation(conversationId) {
  await client.delete(`/api/chat/history/${conversationId}`)
  return conversationId
}
