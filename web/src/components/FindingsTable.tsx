import type { Finding } from '../lib/api'

type Props = {
  findings: Finding[]
}

export function FindingsTable({ findings }: Props) {
  return (
    <div className="findings-wrap">
      <div className="findings-meta">
        <h3>Top {findings.length} lessons</h3>
        <p>Ranked from the project records</p>
      </div>
      <div className="findings-scroll">
        <table className="findings-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Lesson</th>
              <th>Category</th>
              <th>Evidence</th>
              <th>Why it was easy to miss</th>
              <th>What to do</th>
              <th>Priority</th>
              <th>Sources</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((row) => (
              <tr key={`${row.rank}-${row.finding}`}>
                <td>{row.rank}</td>
                <td>{row.finding}</td>
                <td>{row.category}</td>
                <td>{row.evidence}</td>
                <td>{row.correlation || '—'}</td>
                <td>{row.recommendation}</td>
                <td>
                  <span className={`priority priority-${row.priority}`}>{row.priority}</span>
                </td>
                <td>{(row.sources || []).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
