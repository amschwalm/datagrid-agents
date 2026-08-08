import { Link } from 'react-router-dom'

export function Landing() {
  return (
    <main className="page hero">
      <p className="hero-kicker">Datagrid · Project closeout</p>
      <h1>Lessons Learned</h1>
      <p className="hero-lead">
        Tell us what happened. We’ll ask follow-ups, run a multi-pass extraction,
        and return a ranked findings table you can keep asking about.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/extract">
          Start extraction
        </Link>
      </div>
    </main>
  )
}
