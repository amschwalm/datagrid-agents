import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ConnectivityGraph } from '../components/ConnectivityGraph'
import { FindingsTable } from '../components/FindingsTable'
import { ReasoningSteps } from '../components/ReasoningSteps'
import {
  continueLessons,
  generateFollowups,
  streamExtractLessons,
  type AgentResult,
  type Finding,
  type LinkEvent,
  type QAItem,
  type ReasoningStep,
} from '../lib/api'

type Step = 'prompt' | 'questions' | 'analyzing' | 'result'
type ChatTurn = { role: 'user' | 'agent'; text: string }

export function LessonsFlow() {
  const [step, setStep] = useState<Step>('prompt')
  const [prompt, setPrompt] = useState('')
  const [questions, setQuestions] = useState<string[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [qIndex, setQIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AgentResult | null>(null)
  const [summary, setSummary] = useState('')
  const [actions, setActions] = useState<string[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [reasoning, setReasoning] = useState<ReasoningStep[]>([])
  const [activeLinks, setActiveLinks] = useState<LinkEvent[]>([])
  const [pulseNodes, setPulseNodes] = useState<string[]>([])
  const [completedPasses, setCompletedPasses] = useState(0)
  const [passLine, setPassLine] = useState('')
  const [message, setMessage] = useState('')
  const [chat, setChat] = useState<ChatTurn[]>([])

  const progress = useMemo(() => {
    if (step === 'prompt') return 10
    if (step === 'analyzing') return 55 + Math.min(40, completedPasses * 2)
    if (step === 'result') return 100
    if (!questions.length) return 28
    return 20 + Math.round(((qIndex + 1) / questions.length) * 30)
  }, [step, qIndex, questions.length, completedPasses])

  function collected(): QAItem[] {
    return questions.map((question, index) => ({
      question,
      answer: answers[index] || '',
    }))
  }

  function upsertStep(next: ReasoningStep) {
    setReasoning((prev) => {
      const index = prev.findIndex((item) => item.id === next.id)
      if (index === -1) return [...prev, next]
      const copy = [...prev]
      copy[index] = next
      return copy
    })
  }

  async function startInterview() {
    if (!prompt.trim()) return
    setLoading(true)
    setError('')
    try {
      const data = await generateFollowups({
        prompt: prompt.trim(),
      })
      setQuestions(data.questions)
      setAnswers(data.questions.map(() => ''))
      setQIndex(0)
      setStep('questions')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate follow-ups')
    } finally {
      setLoading(false)
    }
  }

  async function digDeeper() {
    setLoading(true)
    setError('')
    try {
      const data = await generateFollowups({
        prompt: prompt.trim(),
        prior: collected(),
      })
      setQuestions((prev) => [...prev, ...data.questions])
      setAnswers((prev) => [...prev, ...data.questions.map(() => '')])
      setQIndex(questions.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate more follow-ups')
    } finally {
      setLoading(false)
    }
  }

  async function runExtract() {
    setLoading(true)
    setError('')
    setReasoning([])
    setActiveLinks([])
    setPulseNodes([])
    setCompletedPasses(0)
    setPassLine('Launching 20 analysis API calls…')
    setChat([])
    setStep('analyzing')

    try {
      const data = await streamExtractLessons(
        {
          prompt: prompt.trim(),
          answers: collected(),
        },
        {
          onStep: upsertStep,
          onPass: (passEvent) => {
            setCompletedPasses(passEvent.completed)
            setPassLine(
              `${passEvent.title}: ${passEvent.finding_count} findings (${passEvent.completed}/${passEvent.total})`,
            )
            if (passEvent.links?.length) {
              setPulseNodes(passEvent.links)
            }
          },
          onLink: (link) => {
            setActiveLinks((prev) => [...prev, link].slice(-24))
            setPulseNodes([link.from, link.to])
          },
        },
      )
      setResult(data.result)
      setSummary(data.summary || data.result.text || '')
      setActions(data.actions || [])
      setFindings(data.findings || [])
      setStep('result')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
      setStep('questions')
    } finally {
      setLoading(false)
    }
  }

  async function sendFollowup() {
    if (!message.trim() || !result) return
    const userText = message.trim()
    setMessage('')
    setChat((prev) => [...prev, { role: 'user', text: userText }])
    setLoading(true)
    setError('')
    try {
      const data = await continueLessons({
        conversation_id: result.conversation_id,
        message: userText,
        prompt: prompt.trim(),
        findings,
      })
      setResult(data.result)
      setChat((prev) => [...prev, { role: 'agent', text: data.reply || data.result.text }])
      if (data.findings?.length) setFindings(data.findings)
      if (data.summary) setSummary(data.summary)
      if (data.actions?.length) setActions(data.actions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Follow-up failed')
    } finally {
      setLoading(false)
    }
  }

  function resetAll() {
    setStep('prompt')
    setQuestions([])
    setAnswers([])
    setQIndex(0)
    setResult(null)
    setSummary('')
    setActions([])
    setFindings([])
    setReasoning([])
    setActiveLinks([])
    setPulseNodes([])
    setCompletedPasses(0)
    setPassLine('')
    setChat([])
    setMessage('')
    setError('')
  }

  const currentQuestion = questions[qIndex]
  const currentAnswer = answers[qIndex] || ''
  const onLastQuestion = qIndex === questions.length - 1

  return (
    <main className="page">
      <section className="panel">
        <p className="progress">Lessons Learned · {progress}%</p>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        {step === 'prompt' && (
          <>
            <h2>Tell me about something</h2>
            <p className="sub">
              Start with the project moment, miss, or win you want captured. We’ll
              ask follow-ups, then run a 20-pass extraction with a live project graph.
            </p>
            <div className="field">
              <label htmlFor="prompt">Opening statement</label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Tell me about the utility buyout that slipped late in Phase 2…"
              />
            </div>
            <div className="actions">
              <Link className="btn" to="/">
                Back
              </Link>
              <button
                className="btn btn-primary"
                disabled={loading || !prompt.trim()}
                onClick={startInterview}
              >
                {loading ? 'Building follow-ups…' : 'Continue'}
              </button>
            </div>
            <p className="status-line">
              {loading ? 'Generating interview questions…' : ''}
            </p>
            {error && <p className="error">{error}</p>}
          </>
        )}

        {step === 'questions' && currentQuestion && (
          <>
            <h2>A few more details</h2>
            <p className="sub">
              Question {qIndex + 1} of {questions.length}. Answer in plain
              language — this becomes the archive brief.
            </p>
            <p className="question-title">{currentQuestion}</p>
            <div className="field">
              <label htmlFor="answer">Your answer</label>
              <textarea
                id="answer"
                value={currentAnswer}
                onChange={(e) =>
                  setAnswers((prev) => {
                    const next = [...prev]
                    next[qIndex] = e.target.value
                    return next
                  })
                }
                placeholder="Write in plain language…"
              />
            </div>
            <div className="actions">
              <button
                className="btn"
                disabled={loading}
                onClick={() => {
                  if (qIndex === 0) setStep('prompt')
                  else setQIndex((i) => i - 1)
                }}
              >
                Back
              </button>
              {!onLastQuestion ? (
                <button
                  className="btn btn-primary"
                  disabled={loading || !currentAnswer.trim()}
                  onClick={() => setQIndex((i) => i + 1)}
                >
                  Next
                </button>
              ) : (
                <>
                  <button
                    className="btn"
                    disabled={loading || !currentAnswer.trim()}
                    onClick={digDeeper}
                  >
                    {loading ? 'Asking more…' : 'Dig deeper'}
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={loading || !currentAnswer.trim()}
                    onClick={runExtract}
                  >
                    Extract lessons
                  </button>
                </>
              )}
            </div>
            {error && <p className="error">{error}</p>}
          </>
        )}

        {step === 'analyzing' && (
          <>
            <h2>Running multi-pass extraction</h2>
            <p className="sub">
              The orchestrator is fanning out twenty specialized API analyses in
              parallel — cross-linking RFIs, meetings, change events, and more —
              then aggregating the top 50 findings.
            </p>
            <div className="analysis-layout">
              <ConnectivityGraph
                activeLinks={activeLinks}
                pulseNodes={pulseNodes}
                completedPasses={completedPasses}
                totalPasses={20}
              />
              <ReasoningSteps steps={reasoning} passLine={passLine} />
            </div>
            <p className="status-line">
              {loading ? 'Agents working — keep this tab open…' : ''}
            </p>
            {error && <p className="error">{error}</p>}
          </>
        )}

        {step === 'result' && result && (
          <>
            <h2>Extracted lessons</h2>
            <p className="sub">
              From {result.agent_name}. Cross-referenced across 20 analysis passes.
              Ask follow-up questions below.
            </p>
            {summary ? <div className="result summary-block">{summary}</div> : null}
            {actions.length > 0 && (
              <div className="actions-block">
                <h3>Institutional actions</h3>
                <ol>
                  {actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
              </div>
            )}
            <FindingsTable findings={findings} />
            <div className="chat-box">
              <h3 className="chat-title">Ask a follow-up</h3>
              <div className="chat-log">
                {chat.map((turn, index) => (
                  <div key={`${turn.role}-${index}`} className={`chat-turn ${turn.role}`}>
                    <span>{turn.role === 'user' ? 'You' : 'Extractor'}</span>
                    <p>{turn.text}</p>
                  </div>
                ))}
              </div>
              <div className="field">
                <label htmlFor="message">Follow-up question</label>
                <textarea
                  id="message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Which findings should we institutionalize first for utilities?"
                />
              </div>
              <div className="actions">
                <button className="btn" onClick={resetAll}>
                  Start over
                </button>
                <button
                  className="btn btn-primary"
                  disabled={loading || !message.trim()}
                  onClick={sendFollowup}
                >
                  {loading ? 'Thinking…' : 'Send'}
                </button>
              </div>
              <p className="status-line">{loading ? 'Updating lessons conversation…' : ''}</p>
              {error && <p className="error">{error}</p>}
            </div>
          </>
        )}
      </section>
    </main>
  )
}
