// Formatting helpers for the admin console. Plain functions, kept out of the
// component files so React's fast refresh can hot-reload those cleanly.

// The backend stores UTC without a "Z". JavaScript reads a bare timestamp
// as *local* time, which would silently shift every date by the viewer's
// UTC offset (+5 hours in Pakistan). Marking it as UTC fixes that.
export function parseUtc(iso) {
  if (!iso) return null
  let s = String(iso).replace(/(\.\d{3})\d+/, '$1')
  if (!/[zZ]$|[+-]\d\d:\d\d$/.test(s)) s += 'Z'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDateTime(iso) {
  const d = parseUtc(iso)
  if (!d) return '—'
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function formatDate(iso) {
  const d = parseUtc(iso)
  if (!d) return '—'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function timeAgo(iso) {
  const d = parseUtc(iso)
  if (!d) return '—'
  const secs = Math.round((Date.now() - d.getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} d ago`
  return formatDate(iso)
}

export function formatNumber(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString()
}

export function compactNumber(n) {
  if (n === null || n === undefined) return '—'
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

const ACTION_LABELS = {
  'user.suspend': 'Suspended an account',
  'user.reactivate': 'Reactivated an account',
  'user.role_change': 'Changed an account role',
  'user.delete': 'Deleted an account',
  'appeal.resolve': 'Decided a score dispute',
  'feedback.export': 'Exported the retraining dataset',
}

export function actionLabel(action) {
  return ACTION_LABELS[action] || action
}
