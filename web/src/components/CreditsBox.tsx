import type { CreditsUsage } from '../lib/api'

type Props = {
  credits?: CreditsUsage | null
}

function formatCredits(value: number): string {
  if (!Number.isFinite(value)) return '—'
  if (Number.isInteger(value)) return String(value)
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

export function CreditsBox({ credits }: Props) {
  if (!credits || credits.consumed == null) return null

  return (
    <div className="credits-box" aria-live="polite">
      <div className="credits-box-head">
        <h3>Credits used</h3>
        <p>Datagrid usage for this extraction run</p>
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
