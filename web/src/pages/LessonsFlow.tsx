import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ConnectivityGraph } from '../components/ConnectivityGraph'
import { CreditsBox } from '../components/CreditsBox'
import { ElapsedClock } from '../components/ElapsedClock'
import { FindingsTable } from '../components/FindingsTable'
import { KeyFindings } from '../components/KeyFindings'
import { ReasoningSteps } from '../components/ReasoningSteps'
import {
  checkApiHealth,
  confirmProject,
  continueLessons,
  discoverProjects,
  generateFollowups,
  streamExtractLessons,
  type AccessibleProject,
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
  const [discoveredProjects, setDiscoveredProjects] = useState<AccessibleProject[]>([])
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
  const [extraContext, setExtraContext] = useState('')
  const [contextNotes, setContextNotes] = useState<string[]>([])
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

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const health = await checkApiHealth()
        if (cancelled) return
        const routes = health.routes || []
        const missing = [
          '/api/context/confirm-project',
          '/api/context/discover-projects',
        ].filter((route) => !routes.includes(route))
        if (missing.length) {
          setError(
            `API is running but missing routes: ${missing.join(', ')}. ` +
              'In Terminal 1: lsof -ti:8000 | xargs kill -9 ; then from ~/Desktop/lessons-learned on main run ' +
              'source .venv/bin/activate && python -m uvicorn server.app:app --reload --port 8000',
          )
          setPassLine('Stale API server — kill port 8000 and restart uvicorn from main')
        }
      } catch (err) {
        if (cancelled) return
        setError(
          err instanceof Error
            ? err.message
            : 'API not reachable on port 8000 — start uvicorn first',
        )
        setPassLine('API not reachable on http://127.0.0.1:8000')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  function collected(): QAItem[] {
    return questions.map((question, index) => ({
      question,
      answer: answers[index] || '',
    }))
  }

  function answersWithContext(addedContext?: string): QAItem[] {
    const base = collected()
    const notes = [...contextNotes]
    const incoming = (addedContext || '').trim()
    if (incoming) notes.push(incoming)
    if (!notes.length) return base
    return [
      ...base,
      {
        question: 'Additional project context from the team',
        answer: notes.map((note, index) => `${index + 1}. ${note}`).join('\n'),
      },
    ]
  }

  function upsertStep(next: ReasoningStep) {
    setReasoning((prev) => mergeReasoning(prev, [next]))
  }

  function pushLocalSteps(steps: ReasoningStep[]) {
    setReasoning((prev) => mergeReasoning(prev, steps))
  }

  async function confirmProjectAccess(nameOverride?: string) {
    const requested = (nameOverride ?? project).trim()
    if (!requested) return
    if (nameOverride) setProject(requested)
    setLoading(true)
    setError('')
    setConfirmation(null)
    setPassLine(`Checking project files for “${requested}”…`)
    pushLocalSteps([
      {
        id: 'local-ask',
        label: 'Got the project name',
        status: 'done',
        detail: requested,
      },
      {
        id: 'local-search',
        label: 'Checking project files',
        status: 'running',
        detail: 'Looking for this job in your uploaded project records…',
      },
    ])
    try {
      const data = await confirmProject({ project: requested })
      setConfirmation(data)
      if (data.accessible_projects?.length) {
        setDiscoveredProjects(data.accessible_projects)
      }
      setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      if (data.matched) {
        const kind = data.match_kind === 'fuzzy' ? 'Close match' : 'Project found'
        const canonical = data.project_name || data.knowledge_name || requested
        setProject(canonical)
        setPassLine(`${kind}: ${canonical}`)
        upsertStep({
          id: 'local-search',
          label: kind,
          status: 'done',
          detail: data.rationale || canonical,
        })
      } else {
        setPassLine('Project not found in your files')
        upsertStep({
          id: 'local-search',
          label: 'Project not found',
          status: 'partial',
          detail: data.rationale || 'Upload this job’s files, then try again',
        })
      }
      setStep('confirm')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check that project')
      upsertStep({
        id: 'local-search',
        label: 'Could not check project',
        status: 'error',
        detail: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setLoading(false)
    }
  }

  async function discoverAccessibleProjects() {
    setLoading(true)
    setError('')
    setPassLine('Listing projects in your files…')
    pushLocalSteps([
      {
        id: 'discover',
        label: 'Looking up available projects',
        status: 'running',
        detail: 'Scanning uploaded project records for job names…',
      },
    ])
    try {
      const data = await discoverProjects()
      setDiscoveredProjects(data.accessible_projects || [])
      if (data.reasoning?.length) {
        setReasoning((prev) => mergeReasoning(prev, data.reasoning || []))
      } else {
        upsertStep({
          id: 'discover',
          label: `Found ${(data.accessible_projects || []).length} project(s)`,
          status: 'done',
          detail: (data.accessible_projects || []).map((p) => p.name).slice(0, 6).join(', '),
        })
      }
      setPassLine(
        data.accessible_projects?.length
          ? `${data.accessible_projects.length} project(s) found — pick one`
          : 'No projects found in your files yet',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not list projects')
      upsertStep({
        id: 'discover',
        label: 'Could not list projects',
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
    setPassLine('Preparing a few scope questions…')
    pushLocalSteps([
      {
        id: 'scope-start',
        label: 'Preparing scope questions',
        status: 'running',
        detail: `Getting ready for ${confirmedName}`,
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
          detail: `${data.questions.length} quick questions before we dig in`,
        })
      }
      setPassLine(`${data.questions.length} questions ready`)
      setStep('questions')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not prepare scope questions')
    } finally {
      setLoading(false)
    }
  }

  async function digDeeper() {
    setLoading(true)
    setError('')
    setPassLine('Adding a few more questions…')
    pushLocalSteps([
      {
        id: `scope-more-${questions.length}`,
        label: 'Adding more detail questions',
        status: 'running',
        detail: 'Preparing a couple more questions…',
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
          label: 'Added more questions',
          status: 'done',
          detail: `${data.questions.length} more questions`,
        })
      }
      setPassLine(`Added ${data.questions.length} more questions`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add more questions')
    } finally {
      setLoading(false)
    }
  }

  async function runExtract(options?: { addedContext?: string }) {
    if (!confirmation?.matched) return
    const addedContext = (options?.addedContext || '').trim()
    const extractAnswers = answersWithContext(addedContext)
    if (addedContext) {
      setContextNotes((prev) => [...prev, addedContext])
      setExtraContext('')
    }
    setLoading(true)
    setError('')
    setActiveLinks([])
    setPulseNodes([])
    setCompletedPasses(0)
    setCredits(null)
    setPassLine(
      addedContext
        ? 'Re-running with your added project context…'
        : 'Starting the project review…',
    )
    setChat([])
    setEndedAt(null)
    setStartedAt(Date.now())
    setStep('analyzing')
    upsertStep({
      id: 'extract-launch',
      label: addedContext ? 'Re-running with added context' : 'Starting project review',
      status: 'running',
      detail: addedContext
        ? `Adding context, then reviewing ${project.trim()}`
        : `Reviewing ${project.trim()}`,
    })

    try {
      const confirmedName =
        confirmation.project_name || confirmation.knowledge_name || project.trim()
      const data = await streamExtractLessons(
        {
          project: confirmedName,
          knowledge_id: confirmation.knowledge_id || '',
          knowledge_name: confirmation.knowledge_name || confirmedName,
          answers: extractAnswers,
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
              `${passEvent.title}: ${passEvent.finding_count} lessons (${passEvent.completed}/${passEvent.total})${reasoningBit}`,
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
      const agentResult =
        data.result ||
        ({
          role: 'lessons_extractor',
          agent_id: '',
          agent_name: 'Lessons Learned',
          text: data.summary || '',
          conversation_id: null,
        } satisfies AgentResult)
      setResult(agentResult)
      setSummary(data.summary || agentResult.text || '')
      setActions(data.actions || [])
      setFindings(data.findings || [])
      setCredits(data.credits || null)
      setEndedAt(Date.now())
      setPassLine(
        data.credits
          ? `Done — ${data.findings?.length || 0} lessons · ${data.credits.consumed} credits`
          : `Done — ${data.findings?.length || 0} lessons ready`,
      )
      setStep('result')
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Could not finish the review'
      setError(detail)
      setEndedAt(Date.now())
      upsertStep({
        id: 'extract-launch',
        label: 'Review did not finish',
        status: 'error',
        detail,
      })
      setPassLine('Review did not finish — you can try again')
      // Stay on the reviewing screen so progress/error stay visible.
      setStep('analyzing')
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
    setPassLine('Working on your question…')
    pushLocalSteps([
      {
        id: `chat-${chat.length + 1}`,
        label: 'Answering your question',
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
    setDiscoveredProjects([])
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
    setExtraContext('')
    setContextNotes([])
    setError('')
    setStartedAt(null)
    setEndedAt(null)
  }

  const currentQuestion = questions[qIndex]
  const currentAnswer = answers[qIndex] || ''
  const onLastQuestion = qIndex === questions.length - 1
  const showReasoning =
    step !== 'result' && (reasoning.length > 0 || loading || step === 'analyzing')

  return (
    <main
      className={`page${
        step === 'analyzing' || step === 'result' ? ' page-analysis' : ''
      }`}
    >
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

        <div className={showReasoning && step !== 'analyzing' ? 'flow-layout' : undefined}>
          <div className="flow-main">
            {step === 'project' && (
              <>
                <h2>Which project?</h2>
                <p className="sub">
                  Type the job name, or show the projects already in your files and pick
                  one.
                </p>
                <div className="field">
                  <label htmlFor="project">Project name</label>
                  <textarea
                    id="project"
                    value={project}
                    onChange={(e) => {
                      setProject(e.target.value)
                      setConfirmation(null)
                    }}
                    placeholder="e.g. The Harken Apartments / Mt. Pleasant Data Center"
                  />
                </div>
                <div className="actions">
                  <Link className="btn" to="/">
                    Back
                  </Link>
                  <button
                    className="btn"
                    disabled={loading}
                    onClick={discoverAccessibleProjects}
                  >
                    {loading ? 'Looking…' : 'Show my projects'}
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={loading || !project.trim()}
                    onClick={() => confirmProjectAccess()}
                  >
                    {loading ? 'Checking…' : 'Find this project'}
                  </button>
                </div>
                {discoveredProjects.length > 0 ? (
                  <div className="alt-list">
                    <p className="sub">Projects in your files — click one:</p>
                    <ul>
                      {discoveredProjects.map((alt) => (
                        <li key={`${alt.knowledge_id || alt.name}`}>
                          <button
                            className="btn"
                            type="button"
                            disabled={loading}
                            onClick={() => confirmProjectAccess(alt.name)}
                          >
                            Use {alt.name}
                          </button>
                          {alt.notes ? <span className="alt-notes">{alt.notes}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <p className="status-line">{passLine}</p>
                {error && <p className="error">{error}</p>}
              </>
            )}

            {step === 'confirm' && confirmation && (
              <>
                <h2>
                  {confirmation.matched ? 'Project found' : 'Project not found'}
                </h2>
                <p className="sub">
                  {confirmation.matched
                    ? confirmation.match_kind === 'fuzzy'
                      ? 'Close match — we found a similar job name in your files. Confirm it’s the right one before continuing.'
                      : 'We found this job in your project files. Continue when you’re ready.'
                    : 'We couldn’t find that job in your files. Upload the project records, or pick a project below.'}
                </p>

                {confirmation.matched ? (
                  <div className="verified-banner">
                    <span>Ready to continue</span>
                    <strong>
                      {confirmation.project_name || confirmation.knowledge_name}
                    </strong>
                    <em>
                      {(confirmation.match_kind || 'exact') === 'fuzzy'
                        ? 'CLOSE MATCH'
                        : 'MATCHED'}
                    </em>
                  </div>
                ) : (
                  <div className="upload-callout">
                    <h3>Not found</h3>
                    <p>
                      “{confirmation.project}” isn’t in the project files we can see.
                      Upload the job folder (drawings, RFIs, meetings, changes, etc.),
                      then try again — or pick a project below.
                    </p>
                  </div>
                )}

                <div className="confirm-card">
                  <p>
                    <span>You entered</span>
                    <strong>{confirmation.project}</strong>
                  </p>
                  <p>
                    <span>Match</span>
                    <strong className={`match-kind kind-${confirmation.match_kind || 'none'}`}>
                      {confirmation.matched
                        ? `${
                            (confirmation.match_kind || 'exact') === 'fuzzy'
                              ? 'CLOSE'
                              : 'EXACT'
                          } · ${
                            confirmation.project_name || confirmation.knowledge_name
                          }`
                        : 'NOT FOUND'}
                    </strong>
                  </p>
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

                <div className="alt-list">
                  <p className="sub">
                    {confirmation.matched
                      ? 'Or switch to another project:'
                      : 'Projects we can see in your files:'}
                  </p>
                  {(confirmation.accessible_projects?.length ||
                    discoveredProjects.length ||
                    confirmation.alternatives?.length) ? (
                    <ul>
                      {(confirmation.accessible_projects?.length
                        ? confirmation.accessible_projects
                        : discoveredProjects.length
                          ? discoveredProjects
                          : confirmation.alternatives || []
                      ).map((alt) => {
                        const name = alt.name
                        const notes = 'notes' in alt ? alt.notes : undefined
                        return (
                          <li key={`${alt.knowledge_id || name}`}>
                            <button
                              className="btn"
                              type="button"
                              disabled={loading}
                              onClick={() => confirmProjectAccess(name)}
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
                      No project names turned up yet. Upload job files and try again.
                    </p>
                  )}
                </div>

                {confirmation.matched && confirmation.match_kind === 'fuzzy' ? (
                  <div className="upload-callout">
                    <h3>Double-check this job</h3>
                    <p>
                      Continue only if this is the right project. Otherwise pick another
                      one from the list.
                    </p>
                  </div>
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
                    className="btn"
                    disabled={loading}
                    onClick={discoverAccessibleProjects}
                  >
                    {loading ? 'Looking…' : 'Refresh project list'}
                  </button>
                  {confirmation.matched ? (
                    <button
                      className="btn btn-primary"
                      disabled={loading}
                      onClick={startScopeQuestions}
                    >
                      {loading
                        ? 'Getting ready…'
                        : confirmation.match_kind === 'fuzzy'
                          ? 'Yes, continue'
                          : 'Continue'}
                    </button>
                  ) : null}
                </div>
                <p className="status-line">{passLine}</p>
                {error && <p className="error">{error}</p>}
              </>
            )}

            {step === 'questions' && currentQuestion && (
              <>
                <h2>A few quick questions</h2>
                <p className="sub">
                  Question {qIndex + 1} of {questions.length} for{' '}
                  <strong>{confirmation?.project_name || project}</strong>. Short answers
                  help us focus on the right phase, trades, and records.
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
                    placeholder="e.g. Focus Phase 2 buyout and RFIs; look hardest at meetings and change events…"
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
                        {loading ? 'Asking more…' : 'Ask me more'}
                      </button>
                      <button
                        className="btn btn-primary"
                        disabled={loading || !currentAnswer.trim()}
                        onClick={() => runExtract()}
                      >
                        Find lessons
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
                <h2>Reviewing the job</h2>
                <p className="sub">
                  Checking RFIs, meetings, changes, and other records on{' '}
                  {confirmation?.project_name || project} for lessons that usually get
                  missed. This can take a few minutes — leave the tab open.
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
                    title="Progress"
                  />
                </div>
                <p className="status-line">
                  {loading ? 'Still working — leave this tab open…' : passLine}
                </p>
                {error ? <p className="error">{error}</p> : null}
                {!loading && error ? (
                  <div className="actions">
                    <button
                      className="btn"
                      onClick={() => {
                        setError('')
                        setStep('questions')
                      }}
                    >
                      Back to questions
                    </button>
                    <button className="btn btn-primary" onClick={() => runExtract()}>
                      Try again
                    </button>
                  </div>
                ) : null}
              </>
            )}

            {step === 'result' && (result || findings.length > 0 || summary) && (
              <>
                <h2>Lessons found</h2>
                <p className="sub">
                  Top lessons for {confirmation?.project_name || project}. Review the
                  summary, dig into the table, then ask a question or add more project
                  context for another run.
                </p>

                <KeyFindings summary={summary} findings={findings} actions={actions} />

                {contextNotes.length > 0 ? (
                  <div className="context-notes">
                    <h3>Context added for this run</h3>
                    <ul>
                      {contextNotes.map((note, index) => (
                        <li key={`${index}-${note.slice(0, 24)}`}>{note}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <FindingsTable findings={findings} />

                <div className="result-panels">
                  <div className="result-panel">
                    <h3>Ask a follow-up</h3>
                    <p className="result-panel-sub">
                      Ask about a lesson, trade, or decision without starting a new run.
                    </p>
                    <div className="chat-log">
                      {chat.map((turn, index) => (
                        <div
                          key={`${turn.role}-${index}`}
                          className={`chat-turn ${turn.role}`}
                        >
                          <span>{turn.role === 'user' ? 'You' : 'Lessons'}</span>
                          <p>{turn.text}</p>
                        </div>
                      ))}
                    </div>
                    <div className="field">
                      <label htmlFor="message">Your question</label>
                      <textarea
                        id="message"
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        placeholder="Which lessons should we carry into the next buyout?"
                      />
                    </div>
                    <div className="actions">
                      <button
                        className="btn btn-primary"
                        disabled={loading || !message.trim() || !result}
                        onClick={sendFollowup}
                      >
                        {loading ? 'Working…' : 'Ask question'}
                      </button>
                    </div>
                  </div>

                  <div className="result-panel">
                    <h3>Add project context</h3>
                    <p className="result-panel-sub">
                      Add missing job detail, then run again so the new context is used
                      in the lessons.
                    </p>
                    <div className="field">
                      <label htmlFor="extra-context">Additional context</label>
                      <textarea
                        id="extra-context"
                        value={extraContext}
                        onChange={(e) => setExtraContext(e.target.value)}
                        placeholder="e.g. Phase 2 buyout was delayed by switchgear lead times; owner directed value engineering on lobby finishes…"
                      />
                    </div>
                    <div className="actions">
                      <button
                        className="btn btn-primary"
                        disabled={loading || !extraContext.trim()}
                        onClick={() => runExtract({ addedContext: extraContext })}
                      >
                        {loading ? 'Starting…' : 'Run again with this context'}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="result-footer">
                  <CreditsBox credits={credits} compact />
                  <div className="actions">
                    <button className="btn" onClick={resetAll}>
                      Start over
                    </button>
                  </div>
                </div>
                <p className="status-line">{passLine}</p>
                {error ? <p className="error">{error}</p> : null}
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
