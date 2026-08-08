import { Link, Outlet } from 'react-router-dom'

export function Layout() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <Link to="/" className="brand">
          Lessons Learned
          <span>Datagrid</span>
        </Link>
        <nav style={{ display: 'flex', gap: '1.25rem' }}>
          <Link className="nav-link" to="/extract">
            Extract
          </Link>
        </nav>
      </header>
      <Outlet />
    </div>
  )
}
