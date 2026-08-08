import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { SurveyFields, fieldsComplete } from '../components/SurveyFields'
import {
  lessonsCloseoutQuestions,
  lessonsProfileFields,
} from '../data/surveys'
import { extractLessons, type AgentResult } from '../lib/api'

type Step = 'profile' | 'questions' | 'result'

export function LessonsFlow() {
  const [step, setStep] = useState<Step>('profile')
  const [profile, setProfile] = useState<Record<string, string>>({})
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [qIndex, setQIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AgentResult | null>(null)

  const question = lessonsCloseoutQuestions[qIndex]
  const progress = useMemo(() => {
    if (step === 'profile') return 8
    if (step === 'result') return 100
    return 20 + Math.round(((qIndex + 1) / lessonsCloseoutQuestions.length) * 70)
  }, [step, qIndex])

  function setProfileField(id: string, value: string) {
    setProfile((prev) => ({ ...prev, [id]: value }))
  }

  function setAnswerField(id: string, value: string) {
    setAnswers((prev) => ({ ...prev, [id]: value }))
  }

  async function runExtract() {
    setLoading(true)
    setError('')
    try {
      const payload = {
        profile,
        answers: lessonsCloseoutQuestions.map((field) => ({
          id: field.id,
          question: field.label,
          answer: answers[field.id] || '',
        })),
      }
      const data = await extractLessons(payload)
      setResult(data.result)
      setStep('result')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <section className="panel">
        <p className="progress">Lessons learned extractor · {progress}%</p>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        {step === 'profile' && (
          <>
            <h2>Who are you?</h2>
            <p className="sub">
              A short profile so the extractor can ground lessons in role,
              project type, and delivery method.
            </p>
            <SurveyFields
              fields={lessonsProfileFields}
              values={profile}
              onChange={setProfileField}
            />
            <div className="actions">
              <Link className="btn" to="/">
                Back
              </Link>
              <button
                className="btn btn-primary"
                disabled={!fieldsComplete(lessonsProfileFields, profile)}
                onClick={() => setStep('questions')}
              >
                Continue
              </button>
            </div>
          </>
        )}

        {step === 'questions' && question && (
          <>
            <h2>Project wrap-up</h2>
            <p className="sub">
              Question {qIndex + 1} of {lessonsCloseoutQuestions.length}. Be
              blunt — this becomes archive material.
            </p>
            <p className="question-title">{question.label}</p>
            <div className="field">
              <label htmlFor={question.id}>Your answer</label>
              <textarea
                id={question.id}
                value={answers[question.id] || ''}
                onChange={(e) => setAnswerField(question.id, e.target.value)}
                placeholder="Write in plain language…"
              />
            </div>
            <div className="actions">
              <button
                className="btn"
                onClick={() => {
                  if (qIndex === 0) setStep('profile')
                  else setQIndex((i) => i - 1)
                }}
              >
                Back
              </button>
              {qIndex < lessonsCloseoutQuestions.length - 1 ? (
                <button
                  className="btn btn-primary"
                  disabled={!((answers[question.id] || '').trim())}
                  onClick={() => setQIndex((i) => i + 1)}
                >
                  Next
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  disabled={loading || !((answers[question.id] || '').trim())}
                  onClick={runExtract}
                >
                  {loading ? 'Extracting…' : 'Extract lessons'}
                </button>
              )}
            </div>
            <p className="status-line">{loading ? 'Calling Lessons Learned Extractor…' : ''}</p>
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
                  setStep('profile')
                  setQIndex(0)
                  setResult(null)
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
