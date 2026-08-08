import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ConnectivityGraph } from '../components/ConnectivityGraph'
import { CreditsBox } from '../components/CreditsBox'
import { ElapsedClock } from '../components/ElapsedClock'
import { FindingsTable } from '../components/FindingsTable'
import { ReasoningSteps } from '../components/ReasoningSteps'
import {
  confirmProject,
  continueLessons,
  generateFollowups,
  streamExtractLessons,
  type AgentResult,
  type CreditsUsage,
  type Finding,
  type LinkEvent,
  type ProjectConfirmResult,
  type QAItem,
  type ReasoningStep,
} from '../lib/api'

type Step = 'project' | 'confirm' | 'questions' | 'analyzing' | 'result'
type ChatTurn = { role: 'user' | 'agent'; text: string }

function mergeReasoning(prev: ReasoningStep[], incoming: ReasoningStep[]): ReasoningStep[] {
  const next = [...prev]
  for (const step of incoming) {
    const index = next.findIndex((item) => item.id === step.id)
    if (index === -1) next.push(step)
    else next[index] = step
  }
  return next
}

export function LessonsFlow() {
  const [step, setStep] = useState<Step>('project')
  const [project, setProject] = useState('')
  const [confirmation, setConfirmation] = useState<ProjectConfirmResult | null>(null)
  const [questions, setQuestions] = useState<string[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [qIndex, setQIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AgentResult | null>(null)
  const [summary, setSummary] = useState('')
  const [actions, setActions] = useState<string[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [credits, setCredits] = useState<CreditsUsage | null>(null)
  const [reasoning, setReasoning] = useState<ReasoningStep[]>([])
  const [activeLinks, setActiveLinks] = useState<LinkEvent[]>([])
  const [pulseNodes, setPulseNodes] = useState<string[]>([])
  const [completedPasses, setCompletedPasses] = useState(0)
  const [passLine, setPassLine] = useState('')
  const [message, setMessage] = useState('')
  const [chat, setChat] = useState<ChatTurn[]>([])
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [endedAt, setEndedAt] = useState<number | null>(null)

  const clockRunning = step === 'analyzing' && startedAt !== null && endedAt === null

  const progress = useMemo(() => {
    if (step === 'project') return 8
    if (step === 'confirm') return 22
    if (step === 'analyzing') return 55 + Math.min(40, completedPasses * 2)
    if (step === 'result') return 100
    if (!questions.length) return 35
    return 30 + Math.round(((qIndex + 1) / questions.length) * 20)
  }, [step, qIndex, questions.length, completedPasses])

  useEffect(() => {
    if (!loading) return
    // Keep a heartbeat status while network calls are in flight.
    const id = window.setInterval(() => {
      setPassLine((prev) => {
        if (step === 'analyzing') return prev
        if (prev.endsWith('…')) return prev.slice(0, -1) + '...'
        if (prev.endsWith('...')) return prev.slice(0, -3) + '…'
        return prev
      })
    }, 900)
    return () => window.clearInterval(id)
  }, [loading, step])

  function collected(): QAItem[] {
    return questions.map((question, index) => ({
      question,
      answer: answers[index] || '',
    }))
  }

  function upsertStep(next: ReasoningStep) {
    setReasoning((prev) => mergeReasoning(prev, [next]))
  }

  function pushLocalSteps(steps: ReasoningStep[]) {
    setReasoning((prev) => mergeReasoning(prev, steps))
  }

  async function confirmProjectAccess() {
    if (!project.trim()) return
    setLoading(true)
    setError('')
    setConfirmation(null)
    setPassLine('Deep searching Datagrid for this project…')
    pushLocalSteps([
      {
        id: 'local-ask',
        label: 'Capturing project name',
        status: 'done',
        detail: project.trim(),
      },
      {
        id: 'local-search',
        label: 'Asking Deep Search to identify the project in files',
        status: 'running',
        detail: 'Matching your request to project names found in accessible documents…',
      },
    ])
    try {
      const data = await confirmProject({ project: project.trim() })
      setConfirmation(data)
      setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      if (data.matched) {
        const kind = data.match_kind === 'fuzzy' ? 'Fuzzy match' : 'Exact match'
        setPassLine(`${kind}: ${data.project_name || data.knowledge_name}`)
      } else {
        setPassLine('No project match in accessible Datagrid data')
      }
      setStep('confirm')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm project in Datagrid')
      upsertStep({
        id: 'local-search',
        label: 'Project confirmation failed',
        status: 'error',
        detail: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setLoading(false)
    }
  }

  async function startScopeQuestions() {
    if (!confirmation?.matched) return
    const confirmedName =
      confirmation.project_name || confirmation.knowledge_name || project.trim()
    if (confirmedName && confirmedName !== project.trim()) {
      setProject(confirmedName)
    }
    setLoading(true)
    setError('')
    setPassLine('Drafting scope-narrowing questions…')
    pushLocalSteps([
      {
        id: 'scope-start',
        label: 'Scoping the extraction',
        status: 'running',
        detail: `Building guidance questions for ${confirmedName}`,
      },
    ])
    try {
      const data = await generateFollowups({
        project: confirmedName,
        knowledge_name: confirmation.knowledge_name || confirmedName,
        prompt: confirmedName,
      })
      setQuestions(data.questions)
      setAnswers(data.questions.map(() => ''))
      setQIndex(0)
      if (data.reasoning?.length) {
        setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      } else {
        upsertStep({
          id: 'scope-start',
          label: 'Scope questions ready',
          status: 'done',
          detail: `${data.questions.length} questions to narrow extraction guidance`,
        })
      }
      setPassLine(`${data.questions.length} scope questions ready`)
      setStep('questions')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate scope questions')
    } finally {
      setLoading(false)
    }
  }

  async function digDeeper() {
    setLoading(true)
    setError('')
    setPassLine('Asking deeper scope questions…')
    pushLocalSteps([
      {
        id: `scope-more-${questions.length}`,
        label: 'Narrowing scope further',
        status: 'running',
        detail: 'Generating additional guidance questions…',
      },
    ])
    try {
      const confirmedName =
        confirmation?.project_name || confirmation?.knowledge_name || project.trim()
      const data = await generateFollowups({
        project: confirmedName,
        knowledge_name: confirmation?.knowledge_name || confirmedName,
        prompt: confirmedName,
        prior: collected(),
      })
      setQuestions((prev) => [...prev, ...data.questions])
      setAnswers((prev) => [...prev, ...data.questions.map(() => '')])
      setQIndex(questions.length)
      if (data.reasoning?.length) {
        setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      } else {
        upsertStep({
          id: `scope-more-${questions.length}`,
          label: 'Added deeper scope questions',
          status: 'done',
          detail: `${data.questions.length} more questions`,
        })
      }
      setPassLine(`Added ${data.questions.length} deeper questions`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate more questions')
    } finally {
      setLoading(false)
    }
  }

  async function runExtract() {
    if (!confirmation?.matched) return
    setLoading(true)
    setError('')
    setActiveLinks([])
    setPulseNodes([])
    setCompletedPasses(0)
    setCredits(null)
    setPassLine('Launching correlative orchestrator fan-out…')
    setChat([])
    setEndedAt(null)
    setStartedAt(Date.now())
    setStep('analyzing')
    upsertStep({
      id: 'extract-launch',
      label: 'Starting multi-pass correlative extraction',
      status: 'running',
      detail: `Project ${project.trim()} · knowledge ${confirmation.knowledge_name}`,
    })

    try {
      const confirmedName =
        confirmation.project_name || confirmation.knowledge_name || project.trim()
      const data = await streamExtractLessons(
        {
          project: confirmedName,
          knowledge_id: confirmation.knowledge_id || '',
          knowledge_name: confirmation.knowledge_name || confirmedName,
          answers: collected(),
        },
        {
          onStep: upsertStep,
          onPass: (passEvent) => {
            setCompletedPasses(passEvent.completed)
            const reasoningBit = passEvent.reasoning
              ? ` — ${passEvent.reasoning}`
              : passEvent.summary
                ? ` — ${passEvent.summary}`
                : ''
            setPassLine(
              `${passEvent.title}: ${passEvent.finding_count} findings (${passEvent.completed}/${passEvent.total})${reasoningBit}`,
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
      setCredits(data.credits || null)
      setEndedAt(Date.now())
      setPassLine(
        data.credits
          ? `Finished with ${data.findings?.length || 0} findings · ${data.credits.consumed} credits`
          : `Finished with ${data.findings?.length || 0} ranked findings`,
      )
      setStep('result')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
      setEndedAt(Date.now())
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
    setPassLine('Working through your follow-up…')
    pushLocalSteps([
      {
        id: `chat-${chat.length + 1}`,
        label: 'Answering follow-up',
        status: 'running',
        detail: userText.slice(0, 160),
      },
    ])
    try {
      const data = await continueLessons({
        conversation_id: result.conversation_id,
        message: userText,
        prompt: project.trim(),
        project: project.trim(),
        findings,
      })
      setResult(data.result)
      setChat((prev) => [...prev, { role: 'agent', text: data.reply || data.result.text }])
      if (data.findings?.length) setFindings(data.findings)
      if (data.summary) setSummary(data.summary)
      if (data.actions?.length) setActions(data.actions)
      if (data.reasoning?.length) {
        setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      } else {
        upsertStep({
          id: `chat-${chat.length + 1}`,
          label: 'Follow-up answered',
          status: 'done',
          detail: (data.reply || '').slice(0, 180),
        })
      }
      setPassLine('Follow-up complete')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Follow-up failed')
    } finally {
      setLoading(false)
    }
  }

  function resetAll() {
    setStep('project')
    setProject('')
    setConfirmation(null)
    setQuestions([])
    setAnswers([])
    setQIndex(0)
    setResult(null)
    setSummary('')
    setActions([])
    setFindings([])
    setCredits(null)
    setReasoning([])
    setActiveLinks([])
    setPulseNodes([])
    setCompletedPasses(0)
    setPassLine('')
    setChat([])
    setMessage('')
    setError('')
    setStartedAt(null)
    setEndedAt(null)
  }

  const currentQuestion = questions[qIndex]
  const currentAnswer = answers[qIndex] || ''
  const onLastQuestion = qIndex === questions.length - 1
  const showReasoning = reasoning.length > 0 || loading || step === 'analyzing'

  return (
    <main className="page">
      <section className="panel">
        <div className="progress-row">
          <p className="progress">Lessons Learned · {progress}%</p>
          <ElapsedClock
            running={clockRunning}
            startedAt={startedAt}
            endedAt={endedAt}
            label={clockRunning ? 'Running' : startedAt ? 'Total time' : 'Elapsed'}
          />
        </div>
        <div className="progress-bar">
          <span style={{ width: `${progress}%` }} />
        </div>

        <div className={showReasoning ? 'flow-layout' : undefined}>
          <div className="flow-main">
            {step === 'project' && (
              <>
                <h2>Which project?</h2>
                <p className="sub">
                  Tell us the project to extract lessons learned from. Deep Search will
                  look through your Datagrid documents and confirm the project name found
                  in the files.
                </p>
                <div className="field">
                  <label htmlFor="project">Project name</label>
                  <textarea
                    id="project"
                    value={project}
                    onChange={(e) => setProject(e.target.value)}
                    placeholder="e.g. Harborview Phase 2 / Metro Utility Expansion"
                  />
                </div>
                <div className="actions">
                  <Link className="btn" to="/">
                    Back
                  </Link>
                  <button
                    className="btn btn-primary"
                    disabled={loading || !project.trim()}
                    onClick={confirmProjectAccess}
                  >
                    {loading ? 'Searching Datagrid…' : 'Find in Datagrid'}
                  </button>
                </div>
                <p className="status-line">{passLine}</p>
                {error && <p className="error">{error}</p>}
              </>
            )}

            {step === 'confirm' && confirmation && (
              <>
                <h2>Project confirmation</h2>
                <p className="sub">
                  {confirmation.matched
                    ? confirmation.match_kind === 'fuzzy'
                      ? 'Fuzzy match — Deep Search found a close project name in your Datagrid files. Confirm it is the right one.'
                      : 'Exact match — Deep Search found this project in your Datagrid files.'
                    : 'No match — Deep Search could not find that project in accessible Datagrid data.'}
                </p>
                <div className="confirm-card">
                  <p>
                    <span>Requested</span>
                    <strong>{confirmation.project}</strong>
                  </p>
                  <p>
                    <span>Match</span>
                    <strong className={`match-kind kind-${confirmation.match_kind || 'none'}`}>
                      {(confirmation.match_kind || 'none').toUpperCase()}
                      {confirmation.matched
                        ? ` · ${confirmation.project_name || confirmation.knowledge_name}`
                        : ''}
                    </strong>
                  </p>
                  <p>
                    <span>Confidence</span>
                    <strong>{confirmation.confidence || 'low'}</strong>
                  </p>
                  {confirmation.knowledge_name ? (
                    <p>
                      <span>Knowledge source</span>
                      <strong>{confirmation.knowledge_name}</strong>
                    </p>
                  ) : null}
                  {confirmation.rationale ? (
                    <p className="confirm-rationale">{confirmation.rationale}</p>
                  ) : null}
                  {confirmation.evidence?.length ? (
                    <ul className="confirm-evidence">
                      {confirmation.evidence.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>

                {!confirmation.matched || confirmation.match_kind === 'fuzzy' ? (
                  <div className="alt-list">
                    <p className="sub">
                      {confirmation.matched
                        ? 'Other projects Deep Search can see:'
                        : 'Projects currently accessible in Datagrid:'}
                    </p>
                    {(confirmation.accessible_projects?.length ||
                      confirmation.alternatives?.length) ? (
                      <ul>
                        {(confirmation.accessible_projects?.length
                          ? confirmation.accessible_projects
                          : confirmation.alternatives || []
                        ).map((alt) => {
                          const name = alt.name
                          const notes = 'notes' in alt ? alt.notes : undefined
                          return (
                            <li key={`${alt.knowledge_id || name}`}>
                              <button
                                className="btn"
                                type="button"
                                onClick={() => {
                                  setProject(name)
                                  setConfirmation(null)
                                  setStep('project')
                                }}
                              >
                                Use {name}
                              </button>
                              {notes ? <span className="alt-notes">{notes}</span> : null}
                            </li>
                          )
                        })}
                      </ul>
                    ) : (
                      <p className="confirm-rationale">
                        No accessible project names were returned from Datagrid.
                      </p>
                    )}
                  </div>
                ) : null}

                {confirmation.upload_required || !confirmation.matched ? (
                  <div className="upload-callout">
                    <h3>No usable match</h3>
                    <p>
                      {confirmation.next_step ||
                        'Upload this project’s data to Datagrid, wait for indexing, then come back and try again.'}
                    </p>
                  </div>
                ) : confirmation.next_step ? (
                  <p className="confirm-rationale">{confirmation.next_step}</p>
                ) : null}

                <div className="actions">
                  <button
                    className="btn"
                    disabled={loading}
                    onClick={() => {
                      setStep('project')
                      setConfirmation(null)
                    }}
                  >
                    Different project
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={loading || !confirmation.matched}
                    onClick={startScopeQuestions}
                  >
                    {loading
                      ? 'Scoping…'
                      : confirmation.match_kind === 'fuzzy'
                        ? 'Use fuzzy match & continue'
                        : 'Continue to scope'}
                  </button>
                </div>
                <p className="status-line">{passLine}</p>
                {error && <p className="error">{error}</p>}
              </>
            )}

            {step === 'questions' && currentQuestion && (
              <>
                <h2>Narrow the scope</h2>
                <p className="sub">
                  Question {qIndex + 1} of {questions.length} for{' '}
                  <strong>{confirmation?.knowledge_name || project}</strong>. Help the
                  extractor confirm the guidance it needs — phases, artifact weight, and
                  how to verify lessons.
                </p>
                <p className="question-title">{currentQuestion}</p>
                <div className="field">
                  <label htmlFor="answer">Your guidance</label>
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
                    placeholder="e.g. Focus buyout + RFIs in Phase 2; verify lessons by recurrence across meetings and change events…"
                  />
                </div>
                <div className="actions">
                  <button
                    className="btn"
                    disabled={loading}
                    onClick={() => {
                      if (qIndex === 0) setStep('confirm')
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
                <p className="status-line">{passLine}</p>
                {error && <p className="error">{error}</p>}
              </>
            )}

            {step === 'analyzing' && (
              <>
                <h2>Running correlative extraction</h2>
                <p className="sub">
                  The orchestrator is fanning out twenty specialized scans across{' '}
                  {confirmation?.knowledge_name || project}, joining buried signals, then
                  synthesizing the top 50 hard-to-find findings.
                </p>
                <div className="analysis-layout">
                  <ConnectivityGraph
                    activeLinks={activeLinks}
                    pulseNodes={pulseNodes}
                    completedPasses={completedPasses}
                    totalPasses={20}
                  />
                  <ReasoningSteps
                    steps={reasoning}
                    passLine={passLine}
                    title="Generative reasoning"
                  />
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
                  {confirmation?.knowledge_name || project}. Cross-correlated across 20
                  analysis passes for buried, multi-source findings. Ask follow-ups below.
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
                <CreditsBox credits={credits} />
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
                      placeholder="Which buried correlations should we institutionalize first?"
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
                  <p className="status-line">{passLine}</p>
                  {error && <p className="error">{error}</p>}
                </div>
              </>
            )}
          </div>

          {showReasoning && step !== 'analyzing' ? (
            <aside className="flow-aside">
              <ReasoningSteps steps={reasoning} passLine={passLine} />
            </aside>
          ) : null}
        </div>
      </section>
    </main>
  )
}
