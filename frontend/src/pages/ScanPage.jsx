import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import { useAuth } from '../context/AuthContext'
import { analyzeProfile } from '../api/trustlens'
import { clearPendingScan, parseScanTarget, savePendingScan, scanPath, SCAN_HELP, targetLabel } from '../lib/scanFlow'
import './ScanPage.css'

// ---------------------------------------------------------------------------
// One scan per username at a time, shared across re-renders.
//
// React's StrictMode runs every effect twice in development (mount, cleanup,
// mount). For most effects that's harmless, but here each run would fire a
// real /analyze-live request: two RapidAPI calls, two rows in the history,
// twice the quota. A once-only ref guard is the wrong fix (CountUp.jsx has
// the story of how that broke every number on the site), so instead both
// runs share the SAME in-flight promise. The second run just subscribes to
// the scan the first one started.
// ---------------------------------------------------------------------------
const inflight = new Map()

function runScan(username) {
  if (!inflight.has(username)) {
    const p = analyzeProfile(username).then(
      (result) => {
        // Drop it shortly after it settles so a deliberate "scan again"
        // later starts a fresh scan rather than reusing this result.
        setTimeout(() => inflight.delete(username), 1500)
        return result
      },
      (err) => {
        // A failure is forgotten at once, so "Try again" really retries.
        inflight.delete(username)
        throw err
      },
    )
    inflight.set(username, p)
  }
  return inflight.get(username)
}

// What a scan actually does, in order. Shown while it runs as a checklist of
// what's being checked, NOT as a fake progress bar: the backend does all of
// this in one request and doesn't report which step it's on, so the page
// doesn't pretend to know.
const STEPS = [
  ['Public profile', 'Followers, following, posts, bio, profile photo'],
  ['Recent posts', 'Likes, comments and captions from the latest posts'],
  ['Fake-account model', 'Trained Random Forest on the account’s own profile'],
  ['Engagement', 'Interaction rate against what’s normal for its size'],
  ['Reel speech', 'Whisper listens to the newest reels and writes down what is said'],
  ['Misinformation', 'Language model on the bio, every caption and the reel speech, cross-checked with scam rules'],
  ['Credential claims', '“Dr.”, “MBBS”, “CFA” and similar in the bio'],
  ['Trust Score', 'Every check that ran, weighed into one score'],
]

function ScanForm({ initial = '' }) {
  const navigate = useNavigate()
  const [value, setValue] = useState(initial)
  const [error, setError] = useState('')

  function submit(e) {
    e.preventDefault()
    const target = parseScanTarget(value)
    if (!target) {
      setError(value.trim() ? SCAN_HELP : 'Type a username first, for example @lahore.eats')
      return
    }
    navigate(scanPath(target.query))
  }

  return (
    <section className="sc-start">
      <div className="tl-pagehead-blob" aria-hidden="true" />
      <div className="tl-wrap-narrow sc-start-inner">
        <span className="tl-eyebrow">New scan</span>
        <h1 className="tl-display sc-start-title">Who are we<br /><span className="tl-grad-text">checking?</span></h1>
        <p className="tl-lede">
          Any public Instagram account. Type the username, or paste a profile link. Paste a reel link and we scan
          whoever posted it, and listen to that reel too.
        </p>

        <form className="sc-start-form" onSubmit={submit} noValidate>
          <label htmlFor="sc-username" className="sc-sr">Instagram username, profile link or reel link</label>
          <div className="tl-scanbar">
            <span className="tl-scanbar-at" aria-hidden="true">@</span>
            <input
              id="sc-username"
              value={value}
              onChange={(e) => { setValue(e.target.value); setError('') }}
              placeholder="username, profile link or reel link"
              autoComplete="off"
              spellCheck="false"
              autoFocus
            />
            <button type="submit" className="tl-btn tl-btn-grad">Scan</button>
          </div>
          {error && <p className="sc-error" role="alert">{error}</p>}
        </form>

        <div className="sc-hints">
          <span className="tl-chip tl-chip-plain">Usually under a minute</span>
          <span className="tl-chip tl-chip-plain">Saved to your dashboard</span>
          <span className="tl-chip tl-chip-plain">Public accounts only</span>
        </div>
      </div>
    </section>
  )
}

// Keyed by username + attempt in the parent, so "Try again" mounts a fresh
// copy with clean state rather than resetting state inside the effect.
function Scanning({ target, onRetry }) {
  const query = target.query
  const label = targetLabel(target)
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [done, setDone] = useState(false)

  useEffect(() => {
    let cancelled = false
    const started = Date.now()
    const tick = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250)

    runScan(query)
      .then((result) => {
        if (cancelled) return
        clearPendingScan()
        setDone(true)
        // A beat to show every check ticked before moving on.
        setTimeout(() => {
          if (!cancelled) {
            navigate(`/results?id=${result.scan_id ?? ''}`, { replace: true, state: { result } })
          }
        }, 650)
      })
      .catch((err) => {
        if (cancelled) return
        if (err.status === 401) {
          // Session ran out mid-way: keep the username and go log in again.
          savePendingScan(query)
          navigate('/login', { replace: true, state: { reason: 'expired' } })
          return
        }
        clearPendingScan()
        setError({ message: err.message || 'Something went wrong. Try again.', kind: err.kind })
      })
      .finally(() => clearInterval(tick))

    return () => {
      cancelled = true
      clearInterval(tick)
    }
  }, [query, navigate])

  if (error) {
    // "not_found" means the username itself is the problem — a real answer
    // came back saying so, quickly. Anything else is Instagram/the network
    // being slow, where a retry genuinely helps. Different message, because
    // telling someone to "check the spelling" when the real cause was a
    // network stall (or the reverse) is its own kind of misleading.
    const notFound = error.kind === 'not_found'
    const isPost = target.kind === 'post'
    return (
      <section className="sc-run">
        <div className="tl-wrap-narrow">
          <div className="sc-fail tl-card tl-card-pad">
            <span className="tl-chip tl-chip-bad">
              {notFound ? (isPost ? 'Post not found' : 'Account not found') : 'Scan didn’t finish'}
            </span>
            <h1 className="tl-display sc-fail-title">
              {notFound
                ? (isPost ? `We couldn’t find ${label}.` : `${label} doesn’t exist on Instagram.`)
                : `We couldn’t check ${label}.`}
            </h1>
            <p className="tl-lede">{error.message}</p>
            <p className="sc-fail-tips">
              {notFound
                ? (isPost
                  ? 'The post may be private or deleted. If you know whose it is, scan their username instead.'
                  : 'Double-check the spelling and try again — this isn’t a network problem, Instagram told us this account doesn’t exist.')
                : 'This looks like Instagram or the network being slow, not a problem with what you typed. A second try usually works.'}
            </p>
            <div className="sc-fail-actions">
              <button className="tl-btn tl-btn-grad" onClick={onRetry}>Try again</button>
              <button className="tl-btn tl-btn-outline" onClick={() => navigate('/scan')}>Scan someone else</button>
            </div>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="sc-run" aria-live="polite">
      <div className="tl-pagehead-blob" aria-hidden="true" />
      <div className="tl-wrap sc-run-grid">
        <div className="sc-run-copy">
          <span className="tl-eyebrow">{done ? 'Scan complete' : 'Scanning now'}</span>
          <h1 className="tl-display sc-run-title">
            {done ? 'Done.' : 'Looking closer at'}
            <br />
            <span className="tl-grad-text">{label}</span>
          </h1>
          <p className="tl-lede">
            {done
              ? 'Opening the full result…'
              : (target.kind === 'post'
                ? 'First we find who posted it, then run every check on that account and listen to this reel. The timer shows how long this scan has taken so far.'
                : 'Every number on the result comes from one of these checks. The timer below shows how long this scan has taken so far.')}
          </p>
          <div className="sc-timer">
            {!done && <span className="tl-spinner" aria-hidden="true" />}
            <span className="tl-mono">{done ? 'Finished' : `${elapsed}s elapsed`}</span>
          </div>
        </div>

        <ol className="sc-steps">
          {STEPS.map(([title, desc], i) => (
            <li
              key={title}
              className={`sc-step ${done ? 'is-done' : ''}`}
              style={{ animationDelay: `${i * 90}ms`, transitionDelay: done ? `${i * 60}ms` : '0ms' }}
            >
              <span className="sc-step-mark" aria-hidden="true">
                {done ? (
                  <svg viewBox="0 0 20 20"><path d="M5 10.5 L8.5 14 L15 6.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                ) : (
                  <span className="sc-step-pulse" style={{ animationDelay: `${i * 0.25}s` }} />
                )}
              </span>
              <span className="sc-step-text">
                <strong>{title}</strong>
                <span>{desc}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function ScanPage() {
  const { user, loading, signedOut } = useAuth()
  const [params] = useSearchParams()
  const [attempt, setAttempt] = useState(0)
  const raw = params.get('u')
  const target = raw ? parseScanTarget(raw) : null

  if (loading) {
    return <PageShell title="Scan" footer={false}><div className="sc-loading"><span className="tl-spinner" /></div></PageShell>
  }

  // Scanning needs an account. Remember who they asked about, and go.
  if (!user) {
    if (signedOut) return <Navigate to="/" replace />
    if (target) {
      savePendingScan(target.query)
      return <Navigate to="/signup" replace />
    }
    return <Navigate to="/login" replace state={{ from: '/scan' }} />
  }

  return (
    <PageShell title={target ? `Scanning ${targetLabel(target)}` : 'New scan'} className="sc-page" footer={!target}>
      {target
        ? <Scanning key={`${target.query}-${attempt}`} target={target} onRetry={() => setAttempt((a) => a + 1)} />
        : <ScanForm initial={raw || ''} />}
    </PageShell>
  )
}

export default ScanPage
