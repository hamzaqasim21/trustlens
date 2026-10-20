import { useEffect, useState } from 'react'
import { formatNumber } from './adminFormat'

// Presentational pieces shared by every admin page. Data loading lives in
// useAdminResource.js and formatting in adminFormat.js.

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="adm-page-header">
      <div>
        {eyebrow && <div className="adm-eyebrow">{eyebrow}</div>}
        <h1 className="adm-title">{title}</h1>
        {subtitle && <p className="adm-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="adm-header-actions">{actions}</div>}
    </header>
  )
}

export function Card({ eyebrow, title, action, children, className = '' }) {
  return (
    <section className={`adm-card ${className}`}>
      {(eyebrow || title || action) && (
        <div className="adm-card-head">
          <div>
            {eyebrow && <div className="adm-card-eyebrow">{eyebrow}</div>}
            {title && <h2 className="adm-card-title">{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function StatTile({ label, value, sub, tone }) {
  return (
    <div className={`adm-stat ${tone ? `adm-stat-${tone}` : ''}`}>
      <span className="adm-stat-label">{label}</span>
      <span className="adm-stat-value">{value}</span>
      {sub && <span className="adm-stat-sub">{sub}</span>}
    </div>
  )
}

export function Pill({ tone = 'neutral', children, title }) {
  return (
    <span className={`adm-pill adm-pill-${tone}`} title={title}>
      <span className="adm-pill-dot" aria-hidden="true" />
      {children}
    </span>
  )
}

const VERDICT_TONE = { Trusted: 'green', 'Moderate Risk': 'amber', 'High Risk': 'red' }

export function VerdictPill({ verdict }) {
  if (!verdict) return <span className="adm-muted">—</span>
  return <Pill tone={VERDICT_TONE[verdict] || 'neutral'}>{verdict}</Pill>
}

export function AppealStatusPill({ status }) {
  if (status === 'pending') return <Pill tone="amber">Pending review</Pill>
  if (status === 'upheld') return <Pill tone="green">Upheld</Pill>
  if (status === 'rejected') return <Pill tone="neutral">Rejected</Pill>
  return <span className="adm-muted">—</span>
}

export function ScoreCell({ score, corrected }) {
  if (corrected !== null && corrected !== undefined) {
    return (
      <span className="adm-score" title="Original model score, then the score after an upheld report">
        <s className="adm-muted">{score}</s> <span className="adm-score-arrow">→</span> <strong>{corrected}</strong>
      </span>
    )
  }
  return <span className="adm-score">{score ?? '—'}</span>
}

export function SlaBadge({ sla }) {
  if (!sla) return null
  if (sla.hours_left === null) {
    return sla.resolved_within_sla
      ? <Pill tone="green">Decided within 48 h</Pill>
      : <Pill tone="red">Decided after 48 h</Pill>
  }
  if (sla.overdue) {
    return <Pill tone="red">Overdue by {Math.abs(sla.hours_left).toFixed(0)} h</Pill>
  }
  const tone = sla.hours_left < 12 ? 'amber' : 'neutral'
  return <Pill tone={tone}>{sla.hours_left.toFixed(0)} h left</Pill>
}

export function EmptyState({ title, children }) {
  return (
    <div className="adm-empty">
      <div className="adm-empty-title">{title}</div>
      {children && <div className="adm-empty-body">{children}</div>}
    </div>
  )
}

export function ErrorBanner({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="adm-error" role="alert">
      <span>{message}</span>
      {onRetry && <button className="adm-btn adm-btn-ghost adm-btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="adm-pagination">
      <span className="adm-muted">{from}–{to} of {formatNumber(total)}</span>
      <div>
        <button className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <button className="adm-btn adm-btn-ghost adm-btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  )
}

// The dialog's inner form is only mounted while open, so every opening
// starts with an empty reason and no leftover error — no reset logic needed.
function DialogForm({
  title, body, confirmLabel = 'Confirm', danger = false,
  reasonLabel, reasonMin = 0, onConfirm, onCancel,
}) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onCancel])

  const needsReason = Boolean(reasonLabel)
  const reasonOk = !needsReason || reason.trim().length >= reasonMin

  async function submit(e) {
    e.preventDefault()
    if (!reasonOk || busy) return
    setBusy(true)
    setError('')
    try {
      await onConfirm(reason.trim())
    } catch (err) {
      setError(err.message || 'That did not work.')
      setBusy(false)
    }
  }

  return (
    <div className="adm-modal-backdrop" onMouseDown={() => !busy && onCancel()}>
      <form
        className="adm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adm-modal-title"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h2 id="adm-modal-title" className="adm-modal-title">{title}</h2>
        {body && <div className="adm-modal-body">{body}</div>}

        {needsReason && (
          <label className="adm-field">
            <span className="adm-field-label">{reasonLabel}</span>
            <textarea
              className="adm-input adm-textarea"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              autoFocus
            />
            <span className="adm-field-hint">Recorded in the audit log.</span>
          </label>
        )}

        {error && <div className="adm-error adm-error-inline">{error}</div>}

        <div className="adm-modal-actions">
          <button type="button" className="adm-btn adm-btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          <button
            type="submit"
            className={`adm-btn ${danger ? 'adm-btn-danger' : 'adm-btn-primary'}`}
            disabled={!reasonOk || busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </form>
    </div>
  )
}

// A confirmation step for anything that changes someone's account. When a
// reason is required it goes straight into the audit log, which is why the
// button stays disabled until one is written.
export function ConfirmDialog({ open, ...props }) {
  return open ? <DialogForm {...props} /> : null
}
