import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Auth.css'

function Login() {
  return (
    <div className="auth-page">
      <Navbar />
      <div className="auth-wrapper">
        <div className="auth-card">
          <div className="auth-eyebrow">WELCOME BACK</div>
          <h1 className="auth-title">Log in to TrustLens</h1>

          <form className="auth-form">
            <label>Email</label>
            <input type="email" placeholder="you@example.com" />

            <label>Password</label>
            <input type="password" placeholder="••••••••" />

            <button type="submit" className="auth-submit">Log in</button>
          </form>

          <p className="auth-footer">
            Don't have an account? <a href="/signup">Sign up</a>
          </p>
        </div>
      </div>
    </div>
  )
}

export default Login