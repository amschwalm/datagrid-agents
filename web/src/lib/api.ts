export type QAItem = {
  question: string
  answer: string
}

export type Finding = {
  rank: number
  finding: string
  category: string
  evidence: string
  recommendation: string
  priority: 'high' | 'med' | 'low' | string
  sources?: string[]
}

export type ReasoningStep = {
  id: string
  label: string
  status: 'running' | 'done' | 'error' | 'partial' | string
  detail?: string
}

export type PassEvent = {
  index: number
  total: number
  completed: number
  lens: string
  title: string
  status: string
  finding_count: number
  summary?: string
  links?: string[]
}

export type LinkEvent = {
  from: string
  to: string
  via?: string
}

export type LessonsExtractResult = {
  ok: boolean
  summary: string
  actions: string[]
  findings: Finding[]
  pass_count: number
  passes_completed: number
  aggregated_locally?: boolean
  graph_nodes?: string[]
  result: AgentResult
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

export type StreamHandlers = {
  onStep?: (step: ReasoningStep) => void
  onPass?: (passEvent: PassEvent) => void
  onLink?: (link: LinkEvent) => void
  onResult?: (result: LessonsExtractResult) => void
  onError?: (message: string) => void
}

function parseSseChunk(
  buffer: string,
  onEvent: (event: string, data: unknown) => void,
): string {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() || ''
  for (const part of parts) {
    const lines = part.split('\n')
    let event = 'message'
    const dataLines: string[] = []
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) continue
    try {
      onEvent(event, JSON.parse(dataLines.join('\n')))
    } catch {
      // ignore malformed chunks
    }
  }
  return rest
}

export async function streamExtractLessons(
  payload: { prompt: string; answers: QAItem[] },
  handlers: StreamHandlers,
): Promise<LessonsExtractResult> {
  const res = await fetch('/api/lessons/extract/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || data.error || `Request failed (${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: LessonsExtractResult | null = null
  let streamError = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = parseSseChunk(buffer, (event, data) => {
      const payloadData = data as Record<string, unknown>
      if (event === 'step') handlers.onStep?.(payloadData as ReasoningStep)
      if (event === 'pass') handlers.onPass?.(payloadData as PassEvent)
      if (event === 'link') handlers.onLink?.(payloadData as LinkEvent)
      if (event === 'result') {
        finalResult = payloadData as LessonsExtractResult
        handlers.onResult?.(finalResult)
      }
      if (event === 'error') {
        streamError = String(payloadData.detail || 'Extraction failed')
        handlers.onError?.(streamError)
      }
    })
  }

  if (streamError) throw new Error(streamError)
  if (!finalResult) throw new Error('Extraction finished without a result')
  return finalResult
}

export function continueLessons(payload: {
  conversation_id?: string | null
  message: string
  prompt?: string
  findings?: Finding[]
}) {
  return request<{
    ok: boolean
    result: AgentResult
    reply: string
    summary?: string | null
    actions?: string[] | null
    findings: Finding[]
  }>('/api/lessons/continue', payload)
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
