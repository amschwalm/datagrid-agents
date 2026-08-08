export type QAItem = {
  question: string
  answer: string
}

async function request<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || data.error || `Request failed (${res.status})`)
  }
  return data as T
}

export type AgentResult = {
  role: string
  agent_id: string
  agent_name: string
  text: string
  conversation_id?: string | null
}

export function generateFollowups(payload: {
  mode: 'lessons' | 'mentor'
  prompt: string
  prior?: QAItem[]
}) {
  return request<{
    ok: boolean
    mode: 'lessons' | 'mentor'
    questions: string[]
    used_fallback: boolean
  }>('/api/context/followups', payload)
}

export function extractLessons(payload: {
  prompt: string
  answers: QAItem[]
}) {
  return request<{ ok: boolean; result: AgentResult }>('/api/lessons/extract', payload)
}

export function startMentor(payload: {
  prompt: string
  followups: QAItem[]
}) {
  return request<{ ok: boolean; mentor: AgentResult; helper: AgentResult }>(
    '/api/mentor/session',
    payload,
  )
}

export function continueMentor(payload: {
  conversation_id?: string | null
  helper_conversation_id?: string | null
  message: string
  prompt?: string
}) {
  return request<{ ok: boolean; mentor: AgentResult; helper: AgentResult }>(
    '/api/mentor/continue',
    payload,
  )
}
