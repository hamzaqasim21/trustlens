import { Link } from 'react-router-dom'

function Navbar() {
  return (
    <nav className="navbar">
      <Link to="/" className="navbar-logo">
        TrustLens
      </Link>
      <div className="navbar-links">
        <Link to="/about">How it works</Link>
        <Link to="/login">Log in</Link>
        <Link to="/signup" className="navbar-cta">Start a scan</Link>
      </div>
    </nav>
  )
}

export default Navbar