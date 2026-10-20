import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { createAppeal } from '../api/trustlens'
import './DisputePanel.css'

const REASON_MIN = 20

const STATUS_TEXT = {
  pending: ['Under review', 'A reviewer decides within 48 hours of when it was filed. The outcome shows up on your dashboard.', 'warn'],
  upheld: ['Upheld', 'The reviewer agreed and corrected the score. The corrected score is shown at the top of this page.', 'ok'],
  rejected: ['Not upheld', 'The reviewer looked at it and the original score stands. Their reasoning is on your dashboard.', 'bad'],
}

// The user half of the appeal mechanism in the scope document: "If a score
// is disputed by an influencer or user, an appeal mechanism allows
// submission of evidence for admin review within 48 hours."
// What happens next is in the admin console (/admin/appeals); the outcome
// comes back to the user on their Dashboard.
function DisputePanel({ scanId, username, scannedWhileLoggedIn, appealStatus }) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  const submittingRef = useRef(false)

  // The scan couldn't be saved, so there's no record to report.
  if (!scanId) return null

  if (done || appealStatus) {
    const [label, body, tone] = done
      ? ['Report submitted', done, 'warn']
      : STATUS_TEXT[appealStatus] || STATUS_TEXT.pending
    return (
      <div className="dp tl-card tl-card-pad" role="status">
        <span className="tl-eyebrow">Your report</span>
        <h3 className="dp-title">Reported · <span className={`dp-tone-${tone}`}>{label}</span></h3>
        <p className="dp-muted">{body}</p>
        <Link to="/dashboard" className="tl-btn tl-btn-outline tl-btn-sm">Follow it on your dashboard</Link>
      </div>
    )
  }

  if (!user || !scannedWhileLoggedIn) {
    return (
      <div className="dp tl-card tl-card-pad">
        <span className="tl-eyebrow">Think this score is wrong?</span>
        <p className="dp-muted">
          Reports are tied to your account. <Link to="/login" className="tl-link">Log in</Link> and scan again to file one.
        </p>
      </div>
    )
  }

  if (!open) {
    return (
      <div className="dp dp-invite tl-card tl-card-pad">
        <span className="tl-eyebrow">Think this score is wrong?</span>
        <h3 className="dp-title">Report this score.</h3>
        <p className="dp-muted">
          A person on the TrustLens team reviews every report within 48 hours. If the evidence holds up, the score is
          corrected, and the case is used to improve the models.
        </p>
        <button className="tl-btn tl-btn-ink" onClick={() => setOpen(true)}>Report this score</button>
      </div>
    )
  }

  async function submit(e) {
    e.preventDefault()
    if (submittingRef.current) return
    submittingRef.current = true
    setBusy(true)
    setError('')
    try {
      const res = await createAppeal(scanId, reason.trim(), evidence.trim())
      setDone(res.message)
    } catch (err) {
      setError(err.message || 'Could not submit the report.')
    } finally {
      setBusy(false)
      submittingRef.current = false
    }
  }

  const reasonLen = reason.trim().length

  return (
    <form className="dp tl-card tl-card-pad" onSubmit={submit}>
      <span className="tl-eyebrow">Report this score</span>
      <h3 className="dp-title">What did we get wrong about @{username}?</h3>

      <label className="tl-field">
        <span>What did the analysis get wrong?</span>
        <textarea
          className="tl-textarea"
          rows={4}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="For example: this account's followers are real, and here's why…"
          maxLength={2000}
        />
        <span className={`dp-count ${reasonLen >= REASON_MIN ? 'is-ok' : ''}`}>
          {reasonLen < REASON_MIN ? `At least ${REASON_MIN} characters (${reasonLen} so far)` : `${reasonLen} / 2000`}
        </span>
      </label>

      <label className="tl-field">
        <span>Link to evidence <span className="dp-muted">(optional)</span></span>
        <input
          className="tl-input"
          type="url"
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
          placeholder="https://…"
        />
      </label>

      {error && <p className="tl-alert tl-alert-bad" role="alert">{error}</p>}

      <div className="dp-actions">
        <button type="button" className="tl-btn tl-btn-soft" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
        <button type="submit" className="tl-btn tl-btn-grad" disabled={busy || reasonLen < REASON_MIN}>
          {busy ? 'Submitting…' : 'Submit report'}
        </button>
      </div>
    </form>
  )
}

export default DisputePanel
