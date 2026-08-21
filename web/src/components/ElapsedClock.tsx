import { useEffect, useState } from 'react'

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

type Props = {
  running: boolean
  startedAt: number | null
  endedAt?: number | null
  label?: string
}

export function ElapsedClock({
  running,
  startedAt,
  endedAt = null,
  label = 'Elapsed',
}: Props) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running || !startedAt) return
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [running, startedAt])

  if (!startedAt) return null
  const end = endedAt ?? now
  const elapsed = Math.max(0, end - startedAt)

  return (
    <div className={`elapsed-clock ${running ? 'running' : 'stopped'}`} aria-live="polite">
      <span className="elapsed-label">{label}</span>
      <span className="elapsed-value">{formatElapsed(elapsed)}</span>
    </div>
  )
}
