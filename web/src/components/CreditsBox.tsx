import type { CreditsUsage } from '../lib/api'

type Props = {
  credits?: CreditsUsage | null
  compact?: boolean
}

function formatCredits(value: number): string {
  if (!Number.isFinite(value)) return '—'
  if (Number.isInteger(value)) return String(value)
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export function CreditsBox({ credits, compact = false }: Props) {
  if (!credits || credits.consumed == null) return null

  if (compact) {
    return (
      <p className="credits-compact" aria-live="polite">
        <span>Credits used</span>
        <strong>{formatCredits(credits.consumed)}</strong>
      </p>
    )
  }

  return (
    <div className="credits-box" aria-live="polite">
      <div className="credits-box-head">
        <h3>Credits used</h3>
        <p>Usage for this lessons run</p>
      </div>
      <p className="credits-total">
        <strong>{formatCredits(credits.consumed)}</strong>
        <span>credits</span>
      </p>
      <dl className="credits-meta">
        <div>
          <dt>Analysis passes</dt>
          <dd>{formatCredits(credits.pass_credits ?? 0)}</dd>
        </div>
        <div>
          <dt>Aggregate</dt>
          <dd>{formatCredits(credits.aggregate_credits ?? 0)}</dd>
        </div>
        <div>
          <dt>Billed calls</dt>
          <dd>{credits.billed_calls ?? '—'}</dd>
        </div>
      </dl>
    </div>
  )
}
