import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  extractLessons,
  generateFollowups,
  type AgentResult,
  type QAItem,
} from '../lib/api'

type Step = 'prompt' | 'questions' | 'result'

export function LessonsFlow() {
  const [step, setStep] = useState<Step>('prompt')
  const [prompt, setPrompt] = useState('')
  const [questions, setQuestions] = useState<string[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [qIndex, setQIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AgentResult | null>(null)

  const progress = useMemo(() => {
    if (step === 'prompt') return 12
    if (step === 'result') return 100
    if (!questions.length) return 35
    return 30 + Math.round(((qIndex + 1) / questions.length) * 60)
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
        mode: 'lessons',
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
        mode: 'lessons',
        prompt: prompt.trim(),
        prior: collected(),
      })
      const nextQuestions = [...questions, ...data.questions]
      setQuestions(nextQuestions)
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
    try {
      const data = await extractLessons({
        prompt: prompt.trim(),
        answers: collected(),
      })
      setResult(data.result)
      setStep('result')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
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
        <p className="progress">Lessons learned extractor · {progress}%</p>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        {step === 'prompt' && (
          <>
            <h2>Tell me about something</h2>
            <p className="sub">
              Start with the project moment, miss, or win you want captured. We’ll
              ask follow-ups from there, then extract the lessons.
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
                    {loading ? 'Extracting…' : 'Extract lessons'}
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

        {step === 'result' && result && (
          <>
            <h2>Extracted lessons</h2>
            <p className="sub">
              From {result.agent_name}. Save this into your project closeout
              package.
            </p>
            <div className="result">{result.text}</div>
            <div className="actions">
              <button
                className="btn"
                onClick={() => {
                  setStep('prompt')
                  setQuestions([])
                  setAnswers([])
                  setQIndex(0)
                  setResult(null)
                  setError('')
                }}
              >
                Start over
              </button>
              <Link className="btn btn-primary" to="/mentor">
                Ask the mentor
              </Link>
            </div>
          </>
        )}
      </section>
    </main>
  )
}
