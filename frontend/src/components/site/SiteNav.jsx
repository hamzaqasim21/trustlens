import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import Brand from './Brand'

const LINKS = [
  { to: '/scan', label: 'Scan' },
  { to: '/comparison', label: 'Compare' },
  { to: '/about', label: 'How it works' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/extension', label: 'Extension' },
]

// The one navigation bar for every public page. It always says whether
// you're logged in — the old landing nav didn't, which is how an existing
// login from days earlier could make a scan open straight into Results
// with no hint as to why.
function SiteNav() {
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close both menus whenever the page changes (adjusting state during
  // render, React's recommended alternative to a reset-in-an-effect).
  const [path, setPath] = useState(location.pathname)
  if (path !== location.pathname) {
    setPath(location.pathname)
    setMenuOpen(false)
    setMobileOpen(false)
  }

  // Click outside / Escape closes the account menu.
  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  // Members-only pages see `signedOut` and go home too, so it doesn't matter
  // which of these two updates React applies first.
  function handleLogout() {
    navigate('/')
    logout()
  }

  // Creator and brand accounts get their own dashboard (scope §10).
  const roleLink = user?.account_type === 'creator' ? { to: '/creator', label: 'Creator studio' }
    : user?.account_type === 'brand' ? { to: '/brand', label: 'Brand tools' } : null

  const firstName = user?.full_name?.split(' ')[0] || 'Account'
  const initial = (user?.full_name || user?.email || '?').charAt(0).toUpperCase()

  return (
    <header className={`tl-nav ${scrolled ? 'is-scrolled' : ''}`}>
      <div className="tl-wrap tl-nav-inner">
        <Brand />

        <nav className="tl-nav-links" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => `tl-nav-link ${isActive ? 'is-active' : ''}`}>
              {l.label}
            </NavLink>
          ))}
        </nav>

        <div className="tl-nav-right">
          {!loading && !user && (
            <>
              <Link to="/login" className="tl-nav-login tl-hide-mobile">Log in</Link>
              <Link to="/signup" className="tl-btn tl-btn-grad tl-btn-sm">Sign up free</Link>
            </>
          )}

          {!loading && user && (
            <>
              <NavLink
                to="/dashboard"
                className={({ isActive }) => `tl-nav-link tl-hide-mobile ${isActive ? 'is-active' : ''}`}
              >
                Dashboard
              </NavLink>
              {roleLink && (
                <NavLink
                  to={roleLink.to}
                  className={({ isActive }) => `tl-nav-link tl-hide-mobile ${isActive ? 'is-active' : ''}`}
                >
                  {roleLink.label}
                </NavLink>
              )}
              <div className="tl-account" ref={menuRef}>
                <button
                  type="button"
                  className="tl-account-btn"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  <span className="tl-avatar tl-avatar-sm" aria-hidden="true">{initial}</span>
                  <span className="tl-account-name">{firstName}</span>
                  <span className="tl-account-caret" aria-hidden="true" />
                </button>
                {menuOpen && (
                  <div className="tl-account-menu" role="menu">
                    <div className="tl-account-who">
                      <strong>{user.full_name}</strong>
                      <span>{user.email}</span>
                    </div>
                    <Link role="menuitem" to="/dashboard" className="tl-account-item">Dashboard</Link>
                    {roleLink && <Link role="menuitem" to={roleLink.to} className="tl-account-item">{roleLink.label}</Link>}
                    <Link role="menuitem" to="/scan" className="tl-account-item">New scan</Link>
                    <Link role="menuitem" to="/settings" className="tl-account-item">Settings</Link>
                    {user.role === 'admin' && (
                      <Link role="menuitem" to="/admin" className="tl-account-item">Admin console</Link>
                    )}
                    <button role="menuitem" type="button" className="tl-account-item tl-account-item-danger" onClick={handleLogout}>
                      Log out
                    </button>
                  </div>
                )}
              </div>
            </>
          )}

          <button
            type="button"
            className="tl-burger"
            aria-label="Menu"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
          >
            <span />
          </button>
        </div>
      </div>

      <div className={`tl-mobile-panel ${mobileOpen ? 'is-open' : ''}`}>
        <div className="tl-wrap">
          {user && <NavLink to="/dashboard" className="tl-nav-link">Dashboard</NavLink>}
          {roleLink && <NavLink to={roleLink.to} className="tl-nav-link">{roleLink.label}</NavLink>}
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className="tl-nav-link">{l.label}</NavLink>
          ))}
          {!user && !loading && (
            <div className="tl-mobile-actions">
              <Link to="/login" className="tl-btn tl-btn-outline tl-btn-sm">Log in</Link>
              <Link to="/signup" className="tl-btn tl-btn-grad tl-btn-sm">Sign up free</Link>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

export default SiteNav
