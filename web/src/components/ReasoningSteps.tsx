import { useEffect, useRef } from 'react'
import type { ReasoningStep } from '../lib/api'

type Props = {
  steps: ReasoningStep[]
  passLine?: string
  title?: string
}

export function ReasoningSteps({
  steps,
  passLine,
  title = 'Live reasoning',
}: Props) {
  const endRef = useRef<HTMLLIElement | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [steps.length, steps[steps.length - 1]?.status, steps[steps.length - 1]?.detail])

  return (
    <div className="reasoning">
      <div className="reasoning-head">
        <h3>{title}</h3>
        {passLine ? <p>{passLine}</p> : <p>Watch each check as it happens.</p>}
      </div>
      {steps.length === 0 ? (
        <p className="reasoning-empty">Waiting for the next reasoning step…</p>
      ) : (
        <ol className="reasoning-list">
          {steps.map((step, index) => (
            <li
              key={`${step.id}-${index}`}
              className={`reasoning-item status-${step.status}`}
              ref={index === steps.length - 1 ? endRef : undefined}
            >
              <span className="reasoning-status">{step.status}</span>
              <div>
                <strong>{step.label}</strong>
                {step.detail ? <p>{step.detail}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
