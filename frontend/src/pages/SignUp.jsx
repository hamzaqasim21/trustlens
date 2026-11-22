import { useEffect, useRef, useState } from 'react'
import { Navigate, Link, useLocation, useSearchParams } from 'react-router-dom'
import AuthSide from '../components/site/AuthSide'
import VerifyCodeForm from '../components/VerifyCodeForm'
import AccountTypePicker from '../components/AccountTypePicker'
import './Auth.css'
import { useAuth } from '../context/AuthContext'
import { afterAuthPath, clearPendingScan, peekPendingScan } from '../lib/scanFlow'

// Mirrors the backend's real rule (auth.py's password_strength_error): 8+
// characters, at least one letter, at least one digit — a password that
// fails any of those would be rejected server-side too, so "Weak" here
// means "the backend will actually reject this," not a vague guess.
function passwordStrength(password) {
  if (!password) return null
  const hasLetter = /[A-Za-z]/.test(password)
  const hasDigit = /[0-9]/.test(password)
  const hasSymbol = /[^A-Za-z0-9]/.test(password)

  if (password.length < 8 || !hasLetter || !hasDigit) {
    return { label: 'Weak', tone: 'bad', level: 1 }
  }
  if (password.length >= 12 && hasSymbol) {
    return { label: 'Strong', tone: 'ok', level: 3 }
  }
  return { label: 'Medium', tone: 'warn', level: 2 }
}

function PasswordRules({ password }) {
  const rules = [
    ['8 or more characters', password.length >= 8],
    ['At least one letter', /[A-Za-z]/.test(password)],
    ['At least one number', /[0-9]/.test(password)],
  ]
  return (
    <ul className="au-rules">
      {rules.map(([label, ok]) => (
        <li key={label} className={ok ? 'is-ok' : ''}>{label}</li>
      ))}
    </ul>
  )
}

function SignUp() {
  const { signup, user } = useAuth()
  const location = useLocation()
  const [params] = useSearchParams()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [accountType, setAccountType] = useState('personal')
  const [showPassword, setShowPassword] = useState(false)
  const [pendingVerification, setPendingVerification] = useState(null) // { email, message } | null
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(() => peekPendingScan())
  const submittingRef = useRef(false) // blocks a fast double-click/Enter+click double-submit

  useEffect(() => { document.title = 'Sign up · TrustLens' }, [])

  const strength = passwordStrength(password)
  const next = params.get('next') || location.state?.from || null

  // The moment verification succeeds, AuthContext sets `user` — that's what
  // actually moves you on (to the waiting scan, or the dashboard). Without
  // this, a successful code entry silently did nothing on screen, so people
  // clicked "Verify" again and the second click legitimately failed ("code
  // already used"), which looked exactly like the correct code being
  // rejected. Real bug, reported by Hamza three times before it was
  // diagnosed properly.
  if (user) {
    return <Navigate to={afterAuthPath(next)} replace />
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (submittingRef.current) return
    submittingRef.current = true
    setError('')
    setLoading(true)
    try {
      const result = await signup(fullName, email, password, accountType)
      setPendingVerification({ email: result.email, message: result.message })
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
      submittingRef.current = false
    }
  }

  function dropPending() {
    clearPendingScan()
    setPending(null)
  }

  const switchTo = `/login${location.search}`

  return (
    <div className="tl-page au-page">
      <AuthSide pending={pending} mode="signup" />

      <section className="au-main">
        <div className="au-main-top">
          <Link to="/" className="au-back">← Home</Link>
          <span className="au-main-switch">Have an account? <Link to={switchTo}>Log in</Link></span>
        </div>

        <div className="au-card">
          {pendingVerification ? (
            <VerifyCodeForm
              email={pendingVerification.email}
              message={pendingVerification.message}
              onBack={() => setPendingVerification(null)}
            />
          ) : (
            <>
              <span className="tl-eyebrow">Create a free account</span>
              <h1 className="tl-display au-title">
                {pending ? <>Almost<br />there.</> : <>Let’s get<br />started.</>}
              </h1>
              {pending && (
                <p className="au-pending">
                  Create an account and the scan of <strong>@{pending}</strong> starts right after.{' '}
                  <button type="button" className="tl-link" onClick={dropPending}>Not now</button>
                </p>
              )}

              <form className="au-form" onSubmit={handleSubmit}>
                <label className="tl-field">
                  <span>Full name</span>
                  <input
                    className="tl-input"
                    type="text"
                    autoComplete="name"
                    placeholder="Your name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    maxLength={100}
                    required
                  />
                </label>

                <label className="tl-field">
                  <span>Email</span>
                  <input
                    className="tl-input"
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                  <span className="tl-hint">We email a 6-digit code here to confirm it’s real before the account works.</span>
                </label>

                <label className="tl-field">
                  <span>Password</span>
                  <span className="au-pw">
                    <input
                      className="tl-input"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      placeholder="At least 8 characters"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      minLength={8}
                      maxLength={72}
                      required
                    />
                    <button type="button" className="au-pw-toggle" onClick={() => setShowPassword((v) => !v)}>
                      {showPassword ? 'Hide' : 'Show'}
                    </button>
                  </span>
                  {strength && (
                    <span className={`au-strength au-strength-${strength.tone}`}>
                      <span className="au-strength-track">
                        {[1, 2, 3].map((n) => <span key={n} className={n <= strength.level ? 'is-on' : ''} />)}
                      </span>
                      <span className="au-strength-label">{strength.label}</span>
                    </span>
                  )}
                  <PasswordRules password={password} />
                </label>

                <div className="tl-field">
                  <span>Account type</span>
                  <AccountTypePicker value={accountType} onChange={setAccountType} disabled={loading} />
                  <span className="tl-hint">You can change this later in Settings.</span>
                </div>

                {error && <p className="tl-alert tl-alert-bad" role="alert">{error}</p>}

                <button type="submit" className="tl-btn tl-btn-grad tl-btn-lg tl-btn-block" disabled={loading}>
                  {loading ? 'Creating account…' : 'Create account'}
                </button>
              </form>

              <p className="au-switch">Already have an account? <Link to={switchTo}>Log in</Link></p>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

export default SignUp
