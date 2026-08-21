import { Link } from 'react-router-dom'

export function Landing() {
  return (
    <main className="page hero">
      <p className="hero-kicker">Project closeout</p>
      <h1>Lessons Learned</h1>
      <p className="hero-lead">
        Pick a project, answer a few quick scope questions, then pull hard-to-spot
        lessons from RFIs, meetings, changes, and the rest of the job file.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/extract">
          Start
        </Link>
      </div>
    </main>
  )
}
