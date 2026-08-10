import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Auth.css'

function SignUp() {
  return (
    <div className="auth-page">
      <Navbar />
      <div className="auth-wrapper">
        <div className="auth-card">
          <div className="auth-eyebrow">GET STARTED</div>
          <h1 className="auth-title">Create your account</h1>

          <form className="auth-form">
            <label>Full name</label>
            <input type="text" placeholder="Your name" />

            <label>Email</label>
            <input type="email" placeholder="you@example.com" />

            <label>Password</label>
            <input type="password" placeholder="••••••••" />

            <button type="submit" className="auth-submit">Create account</button>
          </form>

          <p className="auth-footer">
            Already have an account? <a href="/login">Log in</a>
          </p>
        </div>
      </div>
    </div>
  )
}

export default SignUp