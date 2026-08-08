import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  continueMentor,
  generateFollowups,
  startMentor,
  type AgentResult,
  type QAItem,
} from '../lib/api'

type Step = 'prompt' | 'questions' | 'session'

export function MentorFlow() {
  const [step, setStep] = useState<Step>('prompt')
  const [prompt, setPrompt] = useState('')
  const [questions, setQuestions] = useState<string[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [qIndex, setQIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mentor, setMentor] = useState<AgentResult | null>(null)
  const [helper, setHelper] = useState<AgentResult | null>(null)
  const [message, setMessage] = useState('')

  const progress = useMemo(() => {
    if (step === 'prompt') return 12
    if (step === 'session') return 100
    if (!questions.length) return 35
    return 30 + Math.round(((qIndex + 1) / questions.length) * 55)
  }, [step, qIndex, questions.length])

  function collected(): QAItem[] {
    return questions.map((question, index) => ({
      question,
      answer: answers[index] || '',
    }))
  }

  async function startInterview() {
    if (!prompt.trim()) return
    setLoading(true)
    setError('')
    try {
      const data = await generateFollowups({
        mode: 'mentor',
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
        mode: 'mentor',
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

  async function openSession() {
    setLoading(true)
    setError('')
    try {
      const data = await startMentor({
        prompt: prompt.trim(),
        followups: collected(),
      })
      setMentor(data.mentor)
      setHelper(data.helper)
      setStep('session')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mentor session failed')
    } finally {
      setLoading(false)
    }
  }

  async function sendFollowup() {
    if (!message.trim() || !mentor) return
    setLoading(true)
    setError('')
    try {
      const data = await continueMentor({
        conversation_id: mentor.conversation_id,
        helper_conversation_id: helper?.conversation_id,
        message,
        prompt: prompt.trim(),
      })
      setMentor(data.mentor)
      setHelper(data.helper)
      setMessage('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Follow-up failed')
    } finally {
      setLoading(false)
    }
  }

  const currentQuestion = questions[qIndex]
  const currentAnswer = answers[qIndex] || ''
  const onLastQuestion = qIndex === questions.length - 1

  return (
    <main className="page">
      <section className="panel">
        <p className="progress">Construction mentor · {progress}%</p>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        {step === 'prompt' && (
          <>
            <h2>Tell me about something</h2>
            <p className="sub">
              Start with the live problem or decision. We’ll ask follow-ups to
              sharpen context, then bring in the mentor and lessons support.
            </p>
            <div className="field">
              <label htmlFor="prompt">Opening statement</label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Tell me about buying out the electrical utility package and the risks I’m missing…"
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
            <h2>Sharpen the ask</h2>
            <p className="sub">
              Question {qIndex + 1} of {questions.length}. The more specific you
              are, the sharper the mentoring.
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
                    onClick={openSession}
                  >
                    {loading ? 'Calling agents…' : 'Start mentor session'}
                  </button>
                </>
              )}
            </div>
            <p className="status-line">
              {loading ? 'Working with Datagrid agents…' : ''}
            </p>
            {error && <p className="error">{error}</p>}
          </>
        )}

        {step === 'session' && mentor && helper && (
          <>
            <h2>Mentor session</h2>
            <p className="sub">
              Primary guidance from the Mentor Agent, with a second pass from
              the Lessons Learned Extractor.
            </p>
            <div className="split">
              <div className="result">
                <h3>Mentor</h3>
                {mentor.text}
              </div>
              <div className="result">
                <h3>Lessons support</h3>
                {helper.text}
              </div>
            </div>
            <div className="chat-box">
              <div className="field">
                <label htmlFor="message">Follow-up message</label>
                <textarea
                  id="message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Ask a sharper question…"
                />
              </div>
              <div className="actions">
                <button
                  className="btn"
                  onClick={() => {
                    setStep('prompt')
                    setMentor(null)
                    setHelper(null)
                    setQuestions([])
                    setAnswers([])
                    setQIndex(0)
                    setMessage('')
                    setError('')
                  }}
                >
                  New session
                </button>
                <button
                  className="btn btn-primary"
                  disabled={loading || !message.trim()}
                  onClick={sendFollowup}
                >
                  {loading ? 'Thinking…' : 'Send'}
                </button>
              </div>
              <p className="status-line">
                {loading ? 'Updating mentor + helper…' : ''}
              </p>
              {error && <p className="error">{error}</p>}
            </div>
          </>
        )}
      </section>
    </main>
  )
}
