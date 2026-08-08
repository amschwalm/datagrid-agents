import type { ReasoningStep } from '../lib/api'

type Props = {
  steps: ReasoningStep[]
  passLine?: string
}

export function ReasoningSteps({ steps, passLine }: Props) {
  return (
    <div className="reasoning">
      <div className="reasoning-head">
        <h3>Reasoning</h3>
        {passLine ? <p>{passLine}</p> : null}
      </div>
      <ol className="reasoning-list">
        {steps.map((step) => (
          <li key={`${step.id}-${step.label}`} className={`reasoning-item status-${step.status}`}>
            <span className="reasoning-status">{step.status}</span>
            <div>
              <strong>{step.label}</strong>
              {step.detail ? <p>{step.detail}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
