import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import ScoreRing from '../components/site/ScoreRing'
import RoleGate from '../components/RoleGate'
import { ConfidenceBlock } from '../components/ResultExtras'
import { creatorApi } from '../api/trustlens'
import { useAuth } from '../context/AuthContext'
import { parseUsername, USERNAME_HELP } from '../lib/scanFlow'
import { formatDate, toneFor } from '../lib/verdict'
import './CreatorStudio.css'

// Creator dashboard (scope §10): "Connects their Instagram account ... to
// receive a full audience authenticity report ... Can download a shareable
// Trust Badge certificate to share with brands, and receives tips for
// improving their credibility score."
// Ownership is proven with a code in the bio instead of OAuth; creator.py
// explains why, and the page says so too.

function ClaimStep({ pending, onChanged }) {
  const [input, setInput] = useState(pending?.username || '')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState(null)
  const [copied, setCopied] = useState(false)

  async function start(e) {
    e.preventDefault()
    const u = parseUsername(input)
    if (!u) { setMsg({ ok: false, text: USERNAME_HELP }); return }
    setBusy('start')
    setMsg(null)
    try {
      await creatorApi.startClaim(u)
      await onChanged()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy('')
    }
  }

  async function verify() {
    setBusy('verify')
    setMsg(null)
    try {
      const r = await creatorApi.verifyClaim()
      setMsg({ ok: r.verified, text: r.message })
      if (r.verified) await onChanged()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="cs-card tl-card tl-card-pad">
      <span className="tl-chip tl-chip-ink tl-chip-plain">Step 1 · Prove it’s yours</span>
      <h2>Connect your Instagram account</h2>
      <p className="tl-muted">
        We give you a short code. Put it anywhere in your Instagram bio, press Verify, and TrustLens reads your bio to
        check it’s there. Only the owner can edit a bio, so that proves the account is yours. You can delete the code
        straight after.
      </p>
      <form className="cs-row" onSubmit={start}>
        <div className="tl-scanbar cs-bar">
          <span className="tl-scanbar-at" aria-hidden="true">@</span>
          <input aria-label="Your Instagram username" placeholder="your_username" value={input}
            onChange={(e) => setInput(e.target.value)} autoComplete="off" spellCheck="false" />
          <button type="submit" className="tl-btn tl-btn-grad tl-btn-sm" disabled={Boolean(busy)}>
            {pending ? 'New code' : 'Get my code'}
          </button>
        </div>
      </form>

      {pending && (
        <div className="cs-code">
          <span className="tl-mono">Add this to the bio of @{pending.username}:</span>
          <div className="cs-code-row">
            <code>{pending.code}</code>
            <button type="button" className="tl-btn tl-btn-soft tl-btn-sm"
              onClick={() => navigator.clipboard?.writeText(pending.code).then(() => setCopied(true)).catch(() => {})}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <ol>
            <li>Open Instagram, go to your profile, tap <strong>Edit profile</strong>.</li>
            <li>Paste <strong>{pending.code}</strong> anywhere in your bio and save.</li>
            <li>Come back here and press Verify.</li>
          </ol>
          <button className="tl-btn tl-btn-ink" onClick={verify} disabled={Boolean(busy)}>
            {busy === 'verify' ? 'Reading your bio…' : 'Verify'}
          </button>
        </div>
      )}
      {msg && <p className={`tl-alert ${msg.ok ? 'tl-alert-ok' : 'tl-alert-warn'}`} role="status">{msg.text}</p>}
      <p className="tl-hint cs-why">
        Why not “Log in with Instagram”? Meta only lets apps that have passed its App Review and business verification
        use that for the public. A bio code proves the same thing, ownership, without it.
      </p>
    </div>
  )
}

function Report({ home, onChanged }) {
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState(null)
  const scan = home.scan

  async function runScan() {
    setBusy('scan')
    setMsg(null)
    try {
      const r = await creatorApi.scan()
      if (r.error) setMsg({ ok: false, text: r.error })
      await onChanged()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy('')
    }
  }

  async function badge() {
    setBusy('badge')
    setMsg(null)
    try {
      await creatorApi.issueBadge()
      await onChanged()
      setMsg({ ok: true, text: 'Badge issued. Download the certificate below and share it, or share its check link.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy('')
    }
  }

  const tone = scan ? toneFor(scan.verdict) : 'neutral'
  return (
    <>
      <div className="cs-card tl-card tl-card-pad cs-verified">
        <div className="cs-verified-head">
          <span className="tl-chip tl-chip-ok">Verified owner</span>
          <h2>@{home.claim.username}</h2>
          <span className="tl-hint">Verified {formatDate(home.claim.verified_at)}</span>
        </div>
        <div className="cs-row">
          <button className="tl-btn tl-btn-grad" onClick={runScan} disabled={Boolean(busy)}>
            {busy === 'scan' ? 'Scanning your account…' : scan ? 'Run a fresh report' : 'Run my first report'}
          </button>
          {scan && <Link to={`/results?id=${scan.id}`} className="tl-btn tl-btn-outline">Full result</Link>}
        </div>
        {msg && <p className={`tl-alert ${msg.ok ? 'tl-alert-ok' : 'tl-alert-bad'}`} role="status">{msg.text}</p>}
      </div>

      {scan && (
        <>
          <div className="cs-grid">
            <div className="cs-card tl-card tl-card-pad cs-score">
              <span className="tl-chip tl-chip-ink tl-chip-plain">Your Trust Score</span>
              <ScoreRing score={scan.trust_score} tone={tone} size={200} />
              <span className={`tl-chip tl-chip-${tone}`}>{scan.confidence?.needs_review ? 'Needs review' : scan.verdict}</span>
              <span className="tl-hint">From your report on {formatDate(scan.scanned_at)}</span>
              <ConfidenceBlock confidence={scan.confidence} />
            </div>

            <div className="cs-card tl-card tl-card-pad">
              <span className="tl-chip tl-chip-ink tl-chip-plain">Audience authenticity report</span>
              <h2>How real your audience looks</h2>
              <ul className="cs-signals">
                {home.audience.signals.map((s) => (
                  <li key={s.label} className={`cs-sig-${s.tone}`}>
                    <div><strong>{s.label}</strong><span>{s.detail}</span></div>
                    <b>{s.value}</b>
                  </li>
                ))}
              </ul>
              <p className="tl-hint">{home.audience.limits}</p>
            </div>
          </div>

          <div className="cs-grid">
            <div className="cs-card tl-card tl-card-pad">
              <span className="tl-chip tl-chip-ink tl-chip-plain">Tips</span>
              <h2>How to raise your score</h2>
              <ol className="cs-tips">
                {home.tips.map((t, i) => <li key={i}><strong>{t.area}.</strong> {t.tip}</li>)}
              </ol>
            </div>

            <div className="cs-card tl-card tl-card-pad">
              <span className="tl-chip tl-chip-ink tl-chip-plain">Trust Badge</span>
              <h2>A certificate to share with brands</h2>
              <p className="tl-muted">
                Shows your latest score and confidence, valid for 30 days. Anyone can check it’s genuine with its code, so an
                edited copy can’t fool them. It needs a report from the last 7 days.
              </p>
              <button className="tl-btn tl-btn-grad" onClick={badge} disabled={Boolean(busy)}>
                {busy === 'badge' ? 'Issuing…' : 'Issue a Trust Badge'}
              </button>
              {home.badges.length > 0 && (
                <ul className="cs-badges">
                  {home.badges.map((b) => (
                    <li key={b.code} className={b.valid ? '' : 'is-old'}>
                      <div>
                        <strong>{b.trust_score} · {b.verdict}</strong>
                        <span className="tl-mono">{b.code} · {b.valid ? `valid until ${formatDate(b.expires_at)}` : 'expired'}</span>
                      </div>
                      <div className="cs-badge-acts">
                        <button className="br-linkbtn" onClick={() => creatorApi.downloadBadge(b.code)}>Certificate PDF</button>
                        <Link className="tl-link" to={`/badge/${b.code}`}>Check link</Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

function CreatorStudio() {
  const { user, loading, signedOut } = useAuth()
  const [home, setHome] = useState(null)
  const [error, setError] = useState('')
  const isCreator = user?.account_type === 'creator'

  const load = useCallback(async () => {
    try {
      setHome(await creatorApi.home())
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    if (!isCreator) return
    let cancelled = false
    creatorApi.home()
      .then((h) => { if (!cancelled) setHome(h) })
      .catch((err) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [isCreator])

  if (loading) return null
  if (!user) return <Navigate to={signedOut ? '/' : '/login?next=/creator'} replace />

  return (
    <PageShell title="Creator studio" className="cs-page">
      <section className="tl-pagehead">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap">
          <span className="tl-eyebrow">Creator dashboard</span>
          <h1 className="tl-display tl-pagehead-title">Creator<br /><span className="tl-grad-text">studio.</span></h1>
          <p className="tl-lede tl-pagehead-lede">
            See your account the way brands and followers see it on TrustLens, learn what moves your score, and get a
            Trust Badge certificate they can verify.
          </p>
        </div>
      </section>
      {!isCreator ? (
        <RoleGate type="creator" what="Creator tools" />
      ) : (
        <section className="tl-band tl-band-tint">
          <div className="tl-wrap cs-stack">
            {error && <p className="tl-alert tl-alert-bad">{error}</p>}
            {!home && !error && <div className="cs-loading"><span className="tl-spinner" /></div>}
            {home && (home.claim
              ? <Report home={home} onChanged={load} />
              : <ClaimStep pending={home.pending} onChanged={load} />)}
          </div>
        </section>
      )}
    </PageShell>
  )
}

export default CreatorStudio
