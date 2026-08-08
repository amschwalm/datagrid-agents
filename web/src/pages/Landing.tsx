import { Link } from 'react-router-dom'

export function Landing() {
  return (
    <main className="page hero">
      <p className="hero-kicker">Datagrid · Project closeout</p>
      <h1>Lessons Learned</h1>
      <p className="hero-lead">
        Confirm the project in Datagrid knowledge, narrow the scope, then run a
        correlative multi-pass extraction that surfaces buried findings across sources.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/extract">
          Start extraction
        </Link>
      </div>
    </main>
  )
}
