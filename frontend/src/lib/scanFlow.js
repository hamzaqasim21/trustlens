// ============================================================================
// The "type a username → sign up / log in → see the result" pipeline.
//
// A logged-out visitor who types a username is sent to sign up first. The
// username is remembered here (sessionStorage: this tab only, gone when the
// tab closes) so that the moment they finish signing up or logging in, the
// scan they asked for runs automatically instead of dropping them on the
// Dashboard and making them type it again.
// ============================================================================

const PENDING_KEY = 'trustlens_pending_scan'

// Instagram's own rule: 1-30 characters, letters, numbers, dots, underscores.
const USERNAME_RE = /^[A-Za-z0-9._]{1,30}$/

// Paths on instagram.com that are pages, not accounts.
const NOT_ACCOUNTS = new Set(['p', 'reel', 'reels', 'explore', 'stories', 'accounts', 'direct', 'tv'])

/**
 * Turns whatever someone pasted into a bare username, or null if it can't
 * be one. Accepts "cristiano", "@cristiano", "instagram.com/cristiano" and
 * full profile URLs like "https://www.instagram.com/cristiano/?hl=en".
 * A post or reel link is refused rather than guessed at, since it doesn't
 * say whose account it is.
 */
export function parseUsername(input) {
  let s = (input || '').trim()
  if (!s) return null

  const urlMatch = s.match(/^(?:https?:\/\/)?(?:www\.|m\.)?instagram\.com\/([^/?#\s]+)/i)
  if (urlMatch) {
    const first = urlMatch[1]
    if (NOT_ACCOUNTS.has(first.toLowerCase())) return null
    s = first
  }

  s = s.replace(/^@+/, '')
  return USERNAME_RE.test(s) ? s.toLowerCase() : null
}

export const USERNAME_HELP =
  'Enter an Instagram username like @lahore.eats, or paste a profile link.'

// The scan box also takes a post or reel link: the backend looks up who
// posted it, scans that account, and always listens to that reel
// (scope: "pastes a profile or reel link to receive a Trust Score report").
const POST_RE = /instagram\.com\/(?:([A-Za-z0-9._]{1,30})\/)?(reels?|p|tv)\/([A-Za-z0-9_-]{5,40})/i

/**
 * What the scan box was given: { kind: 'username', username, query } or
 * { kind: 'post', code, owner, isReel, query }, or null. `query` is what is
 * sent to the backend (and kept in the address bar while scanning).
 */
export function parseScanTarget(input) {
  const s = (input || '').trim()
  if (!s) return null
  const m = s.match(POST_RE)
  if (m) {
    const owner = m[1] && !NOT_ACCOUNTS.has(m[1].toLowerCase()) ? m[1].toLowerCase() : null
    const isReel = m[2].toLowerCase() !== 'p'
    const path = `${isReel ? 'reel' : 'p'}/${m[3]}/`
    return { kind: 'post', code: m[3], owner, isReel, query: `instagram.com/${owner ? `${owner}/` : ''}${path}` }
  }
  const username = parseUsername(s)
  return username ? { kind: 'username', username, query: username } : null
}

/** How to name a scan target in a sentence: "@name", "this reel" or "this post". */
export function targetLabel(target) {
  if (!target) return ''
  if (target.kind === 'username') return `@${target.username}`
  return target.isReel ? 'this reel' : 'this post'
}

export const SCAN_HELP =
  'Enter an Instagram username like @lahore.eats, or paste a profile, post or reel link.'

export function savePendingScan(username) {
  try { sessionStorage.setItem(PENDING_KEY, username) } catch { /* storage blocked: the user just types it again */ }
}

export function peekPendingScan() {
  try { return sessionStorage.getItem(PENDING_KEY) } catch { return null }
}

export function clearPendingScan() {
  try { sessionStorage.removeItem(PENDING_KEY) } catch { /* nothing to clear */ }
}

export function scanPath(username) {
  return `/scan?u=${encodeURIComponent(username)}`
}

/**
 * Where to send someone right after they log in or finish signing up:
 * a waiting scan first, then wherever they were headed, then the Dashboard.
 * Only same-site paths are honoured for `next`, so a crafted link can't
 * bounce a freshly logged-in user to another website.
 */
export function afterAuthPath(next) {
  const pending = peekPendingScan()
  if (pending) return scanPath(pending)
  if (next && next.startsWith('/') && !next.startsWith('//')) return next
  return '/dashboard'
}
