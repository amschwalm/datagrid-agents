import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { SurveyFields, fieldsComplete } from '../components/SurveyFields'
import { mentorFollowups, mentorProfileFields } from '../data/surveys'
import {
  continueMentor,
  startMentor,
  type AgentResult,
} from '../lib/api'

type Step = 'profile' | 'prompt' | 'followups' | 'session'

export function MentorFlow() {
  const [step, setStep] = useState<Step>('profile')
  const [profile, setProfile] = useState<Record<string, string>>({})
  const [prompt, setPrompt] = useState('')
  const [followups, setFollowups] = useState<Record<string, string>>({})
  const [fIndex, setFIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mentor, setMentor] = useState<AgentResult | null>(null)
  const [helper, setHelper] = useState<AgentResult | null>(null)
  const [message, setMessage] = useState('')

  const followup = mentorFollowups[fIndex]
  const progress = useMemo(() => {
    if (step === 'profile') return 12
    if (step === 'prompt') return 30
    if (step === 'session') return 100
    return 45 + Math.round(((fIndex + 1) / mentorFollowups.length) * 40)
  }, [step, fIndex])

  async function openSession() {
    setLoading(true)
    setError('')
    try {
      const data = await startMentor({
        profile,
        prompt,
        followups: mentorFollowups.map((field) => ({
          id: field.id,
          question: field.label,
          answer: followups[field.id] || '',
        })),
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
        profile,
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

  return (
    <main className="page">
      <section className="panel">
        <p className="progress">Construction mentor · {progress}%</p>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        {step === 'profile' && (
          <>
            <h2>Who are you?</h2>
            <p className="sub">
              A short intake so the mentor answers in your lane — then a second
              agent brings lessons evidence.
            </p>
            <SurveyFields
              fields={mentorProfileFields}
              values={profile}
              onChange={(id, value) =>
                setProfile((prev) => ({ ...prev, [id]: value }))
              }
            />
            <div className="actions">
              <Link className="btn" to="/">
                Back
              </Link>
              <button
                className="btn btn-primary"
                disabled={!fieldsComplete(mentorProfileFields, profile)}
                onClick={() => setStep('prompt')}
              >
                Continue
              </button>
            </div>
          </>
        )}

        {step === 'prompt' && (
          <>
            <h2>What’s the problem?</h2>
            <p className="sub">
              One clear ask. The follow-ups will sharpen stakes, constraints,
              and what’s already been tried.
            </p>
            <div className="field">
              <label htmlFor="prompt">Initial prompt</label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="I’m buying out the electrical utility package and need the five risks that usually hurt us…"
              />
            </div>
            <div className="actions">
              <button className="btn" onClick={() => setStep('profile')}>
                Back
              </button>
              <button
                className="btn btn-primary"
                disabled={!prompt.trim()}
                onClick={() => setStep('followups')}
              >
                Continue
              </button>
            </div>
          </>
        )}

        {step === 'followups' && followup && (
          <>
            <h2>Sharpen the ask</h2>
            <p className="sub">
              Follow-up {fIndex + 1} of {mentorFollowups.length}.
            </p>
            <p className="question-title">{followup.label}</p>
            <div className="field">
              <label htmlFor={followup.id}>Your answer</label>
              <textarea
                id={followup.id}
                value={followups[followup.id] || ''}
                onChange={(e) =>
                  setFollowups((prev) => ({
                    ...prev,
                    [followup.id]: e.target.value,
                  }))
                }
              />
            </div>
            <div className="actions">
              <button
                className="btn"
                onClick={() => {
                  if (fIndex === 0) setStep('prompt')
                  else setFIndex((i) => i - 1)
                }}
              >
                Back
              </button>
              {fIndex < mentorFollowups.length - 1 ? (
                <button
                  className="btn btn-primary"
                  disabled={!((followups[followup.id] || '').trim())}
                  onClick={() => setFIndex((i) => i + 1)}
                >
                  Next
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  disabled={
                    loading || !((followups[followup.id] || '').trim())
                  }
                  onClick={openSession}
                >
                  {loading ? 'Calling agents…' : 'Start mentor session'}
                </button>
              )}
            </div>
            <p className="status-line">
              {loading ? 'Mentor + Lessons Extractor running…' : ''}
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
                    setStep('profile')
                    setMentor(null)
                    setHelper(null)
                    setFIndex(0)
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
