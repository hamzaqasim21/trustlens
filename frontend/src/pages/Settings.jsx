import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import { useAuth } from '../context/AuthContext'
import { changePassword, deleteAccount, updateProfile } from '../api/trustlens'
import './Settings.css'

// Every button on this page does what it says. The earlier version had
// Save / Update / Delete buttons that did nothing at all, which is exactly
// the kind of fake UI this project doesn't allow; they're now backed by
// real endpoints (PATCH /me, POST /me/password, DELETE /me in main.py).

function Status({ state }) {
  if (!state) return null
  return <p className={`tl-alert ${state.ok ? 'tl-alert-ok' : 'tl-alert-bad'}`} role={state.ok ? 'status' : 'alert'}>{state.text}</p>
}

function ProfileCard({ user, onSaved }) {
  const [name, setName] = useState(user.full_name || '')
  const [busy, setBusy] = useState(false)
  const [state, setState] = useState(null)

  const unchanged = name.trim() === (user.full_name || '').trim()

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setState(null)
    try {
      const updated = await updateProfile(name.trim())
      onSaved(updated)
      setState({ ok: true, text: 'Name updated.' })
    } catch (err) {
      setState({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="st-card tl-card tl-card-pad" onSubmit={save}>
      <div className="st-card-head">
        <span className="st-tag st-tag-green">Profile</span>
        <h2>Your details</h2>
      </div>
      <label className="tl-field">
        <span>Full name</span>
        <input className="tl-input" value={name} onChange={(e) => { setName(e.target.value); setState(null) }} maxLength={100} required />
      </label>
      <label className="tl-field">
        <span>Email</span>
        <input className="tl-input" value={user.email} disabled readOnly />
        <span className="tl-hint">Your email is how you log in and was verified with a code, so it can’t be changed here.</span>
      </label>
      <Status state={state} />
      <button type="submit" className="tl-btn tl-btn-grad" disabled={busy || unchanged || !name.trim()}>
        {busy ? 'Saving…' : 'Save changes'}
      </button>
    </form>
  )
}

function PasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [state, setState] = useState(null)

  const mismatch = confirm.length > 0 && confirm !== next

  async function save(e) {
    e.preventDefault()
    if (next !== confirm) {
      setState({ ok: false, text: 'The new passwords don’t match.' })
      return
    }
    setBusy(true)
    setState(null)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      setState({ ok: true, text: 'Password updated. Use the new one next time you log in.' })
    } catch (err) {
      setState({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="st-card tl-card tl-card-pad" onSubmit={save}>
      <div className="st-card-head">
        <span className="st-tag st-tag-amber">Security</span>
        <h2>Change password</h2>
      </div>
      <label className="tl-field">
        <span>Current password</span>
        <input className="tl-input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
      </label>
      <label className="tl-field">
        <span>New password</span>
        <input className="tl-input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} minLength={8} maxLength={72} required />
        <span className="tl-hint">At least 8 characters, with at least one letter and one number.</span>
      </label>
      <label className="tl-field">
        <span>Confirm new password</span>
        <input className="tl-input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} maxLength={72} required />
        {mismatch && <span className="st-mismatch">Doesn’t match the new password yet.</span>}
      </label>
      <Status state={state} />
      <button type="submit" className="tl-btn tl-btn-ink" disabled={busy || !current || !next || mismatch}>
        {busy ? 'Updating…' : 'Update password'}
      </button>
    </form>
  )
}

function DangerCard({ user }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialogRef = useRef(null)

  useEffect(() => {
    if (open) dialogRef.current?.querySelector('input')?.focus()
  }, [open])

  async function confirmDelete(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await deleteAccount(password)
      logout()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const isAdmin = user.role === 'admin'

  return (
    <div className="st-card st-danger tl-card tl-card-pad">
      <div className="st-card-head">
        <span className="st-tag st-tag-red">Danger zone</span>
        <h2>Delete account</h2>
      </div>
      <p className="st-muted">
        Permanently deletes your account, every scan on it, and any reports you’ve filed. This can’t be undone.
      </p>
      {isAdmin && (
        <p className="tl-alert tl-alert-warn">
          Admin accounts can’t be deleted here. Another admin has to remove your admin role first.
        </p>
      )}

      {!open && (
        <button type="button" className="tl-btn tl-btn-danger" onClick={() => setOpen(true)} disabled={isAdmin}>
          Delete my account
        </button>
      )}

      {open && (
        <form className="st-confirm" onSubmit={confirmDelete} ref={dialogRef}>
          <label className="tl-field">
            <span>Type <strong>DELETE</strong> to confirm</span>
            <input className="tl-input tl-input-mono" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </label>
          <label className="tl-field">
            <span>Your password</span>
            <input className="tl-input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && <p className="tl-alert tl-alert-bad" role="alert">{error}</p>}
          <div className="st-confirm-actions">
            <button type="button" className="tl-btn tl-btn-soft" onClick={() => { setOpen(false); setTyped(''); setPassword(''); setError('') }} disabled={busy}>
              Keep my account
            </button>
            <button type="submit" className="tl-btn tl-btn-danger" disabled={busy || typed !== 'DELETE' || !password}>
              {busy ? 'Deleting…' : 'Delete forever'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

function Settings() {
  const { user, loading, signedOut, applyUserUpdate } = useAuth()

  if (loading) return null
  if (!user) return <Navigate to={signedOut ? '/' : '/login?next=/settings'} replace />

  return (
    <PageShell title="Settings" className="st-page">
      <section className="tl-pagehead">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap">
          <span className="tl-eyebrow">Account</span>
          <h1 className="tl-display tl-pagehead-title">Settings.</h1>
          <p className="tl-lede tl-pagehead-lede">
            Signed in as <strong>{user.email}</strong>. Your scans and reports are on your <Link to="/dashboard" className="tl-link">dashboard</Link>.
          </p>
        </div>
      </section>

      <section className="tl-band tl-band-tint">
        <div className="tl-wrap st-grid">
          <ProfileCard user={user} onSaved={applyUserUpdate} />
          <PasswordCard />
          <DangerCard user={user} />
        </div>
      </section>
    </PageShell>
  )
}

export default Settings
