import { Link } from 'react-router-dom'

export function Landing() {
  return (
    <main className="page hero">
      <p className="hero-kicker">Datagrid · Project intelligence</p>
      <h1>Construction Lessons Learned</h1>
      <p className="hero-lead">
        Two precise tools. Capture what the project taught you, or bring a live
        problem to your construction mentor — with a second agent for evidence.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/lessons">
          Lessons learned survey
        </Link>
        <Link className="btn" to="/mentor">
          Talk to mentor
        </Link>
      </div>
    </main>
  )
}
