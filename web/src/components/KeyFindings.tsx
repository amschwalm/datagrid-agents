import type { Finding } from '../lib/api'

type Props = {
  summary?: string
  findings: Finding[]
  actions?: string[]
}

export function KeyFindings({ summary, findings, actions = [] }: Props) {
  const highlights = findings.slice(0, 5)
  if (!summary && !highlights.length && !actions.length) return null

  return (
    <section className="key-findings">
      <div className="key-findings-head">
        <h3>Summary of key findings</h3>
        <p>Highest-signal takeaways from this job</p>
      </div>
      {summary ? <p className="key-findings-summary">{summary}</p> : null}
      {highlights.length ? (
        <ol className="key-findings-list">
          {highlights.map((item) => (
            <li key={`${item.rank}-${item.finding}`}>
              <div className="key-findings-item">
                <strong>{item.finding}</strong>
                {item.recommendation ? <span>{item.recommendation}</span> : null}
              </div>
              <em className={`priority priority-${item.priority}`}>{item.priority}</em>
            </li>
          ))}
        </ol>
      ) : null}
      {actions.length ? (
        <div className="key-findings-actions">
          <h4>What to do next</h4>
          <ol>
            {actions.slice(0, 5).map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  )
}
