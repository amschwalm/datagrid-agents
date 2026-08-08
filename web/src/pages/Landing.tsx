import { Link } from 'react-router-dom'

export function Landing() {
  return (
    <main className="page hero">
      <p className="hero-kicker">Datagrid · Project intelligence</p>
      <h1>Construction Lessons Learned</h1>
      <p className="hero-lead">
        Start with “tell me about something.” We ask follow-ups to build
        context, then extract lessons or bring in your mentor with evidence.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/lessons">
          Extract lessons
        </Link>
        <Link className="btn" to="/mentor">
          Talk to mentor
        </Link>
      </div>
    </main>
  )
}
