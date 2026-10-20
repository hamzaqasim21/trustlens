import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { adminApi } from '../../api/trustlens'
import { BrandMark } from '../../components/site/Brand'
import './admin.css'

const NAV = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/appeals', label: 'Score reports', badge: 'pending' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/scans', label: 'Scans' },
  { to: '/admin/system', label: 'Models & system' },
  { to: '/admin/audit', label: 'Audit log' },
]

// The page-level guard. It only decides what to *show* — the real
// enforcement is require_admin on every /admin API route, so even someone
// who forces their way onto this page gets nothing back from the server.
function AdminLayout() {
  const { user, loading, logout, signedOut } = useAuth()
  const location = useLocation()
  const [pending, setPending] = useState(null)

  const isAdmin = user?.role === 'admin'

  // The reports badge refreshes whenever the admin moves between pages, so
  // deciding a case updates the count without a full reload.
  useEffect(() => {
    if (!isAdmin) return
    adminApi.appeals('pending')
      .then((r) => setPending(r.items.length))
      .catch(() => setPending(null))
  }, [isAdmin, location.pathname])

  if (loading) return null
  // After pressing Log out here, go home rather than to the login screen.
  if (!user) return <Navigate to={signedOut ? '/' : '/login'} replace state={{ from: location.pathname }} />

  if (!isAdmin) {
    return (
      <div className="adm-denied">
        <div className="adm-denied-code">403</div>
        <h1>This area is for TrustLens administrators</h1>
        <p>
          You're signed in as {user.email}, which doesn't have admin access.
          If you think it should, ask an existing administrator to grant it.
        </p>
        <Link to="/" className="adm-btn adm-btn-primary">Back to TrustLens</Link>
      </div>
    )
  }

  return (
    <div className="adm-shell">
      <aside className="adm-sidebar">
        <Link to="/" className="adm-brand">
          <BrandMark size={26} />
          TrustLens
        </Link>
        <div className="adm-env">ADMIN CONSOLE</div>

        <nav className="adm-nav" aria-label="Admin">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `adm-nav-link ${isActive ? 'adm-nav-active' : ''}`}
            >
              <span>{item.label}</span>
              {item.badge === 'pending' && pending > 0 && (
                <span className="adm-nav-badge" aria-label={`${pending} pending`}>{pending}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="adm-sidebar-foot">
          <div className="adm-whoami">
            <span className="adm-avatar">{(user.full_name || '?').charAt(0).toUpperCase()}</span>
            <div>
              <div className="adm-whoami-name">{user.full_name}</div>
              <div className="adm-whoami-role">Administrator</div>
            </div>
          </div>
          <Link to="/" className="adm-side-link">← Back to the site</Link>
          <button className="adm-side-link" onClick={logout}>Log out</button>
        </div>
      </aside>

      <main className="adm-main">
        <Outlet />
      </main>
    </div>
  )
}

export default AdminLayout
