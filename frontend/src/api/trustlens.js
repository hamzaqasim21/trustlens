// Overridable at build time (VITE_API_BASE=...) for deploying the backend
// somewhere other than this machine; local development needs nothing set.
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000"

// The browser extension talks to its own local gateway, not the website's
// backend. Kept as a separate base URL rather than hidden inside the page so
// all the network endpoints this app knows about stay listed in one file.
const EXTENSION_GATEWAY = "http://127.0.0.1:8100"

function authHeaders() {
  const token = localStorage.getItem('trustlens_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parseErrorMessage(response) {
  try {
    const data = await response.json()
    return (typeof data.detail === 'string' && data.detail) || `Server error: ${response.status}`
  } catch {
    return `Server error: ${response.status}`
  }
}

// Errors carry the HTTP status, so a page can tell "your session ran out"
// (401, send them to log in) apart from "Instagram didn't answer" (retry).
// `kind` (when the backend sends one) further tells "this username doesn't
// exist" (not_found) apart from "Instagram was slow" (network), so the UI
// doesn't have to guess from a message's wording.
function httpError(message, status, kind) {
  const err = new Error(message)
  err.status = status
  if (kind) err.kind = kind
  return err
}

export async function analyzeProfile(username) {
  let response
  try {
    response = await fetch(`${API_BASE}/analyze-live`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ username }),
    })
  } catch {
    throw httpError("Can't reach the TrustLens server. Make sure the backend is running, then try again.", 0)
  }

  if (!response.ok) {
    throw httpError(await parseErrorMessage(response), response.status)
  }

  const data = await response.json()

  if (data.error) {
    throw httpError(data.error, 200, data.kind)
  }

  return data
}

/** A past scan's full saved result, for reopening it from the Dashboard
 * without re-running the scan (no RapidAPI quota spent). */
export async function getSavedResult(scanId) {
  const response = await fetch(`${API_BASE}/scans/${scanId}`, { headers: authHeaders() })
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  return response.json()
}

// ---- Account settings ----
export async function updateProfile(fullName) {
  const response = await fetch(`${API_BASE}/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ full_name: fullName }),
  })
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  return response.json()
}

export async function changePassword(currentPassword, newPassword) {
  const response = await fetch(`${API_BASE}/me/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  return response.json()
}

export async function deleteAccount(password) {
  const response = await fetch(`${API_BASE}/me`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  return response.json()
}

export async function getScanHistory(limit = 20) {
  const response = await fetch(`${API_BASE}/scans?limit=${limit}`, {
    headers: authHeaders(),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function signup(fullName, email, password) {
  const response = await fetch(`${API_BASE}/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name: fullName, email, password }),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function login(email, password) {
  const response = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

export async function verifyEmail(email, code) {
  const response = await fetch(`${API_BASE}/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

/** Live status of the extension's gateway and the models behind it.
 *
 * Deliberately never throws: the gateway not running is the normal case for
 * someone who has not started it yet, not an error state, and the page should
 * say "not running" rather than show a crash. The short timeout stops the page
 * hanging when nothing is listening on that port.
 */
export async function getExtensionStatus() {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 3000)

    const response = await fetch(`${EXTENSION_GATEWAY}/health`, {
      signal: controller.signal,
    })
    clearTimeout(timeout)

    if (!response.ok) return { running: false }
    return { running: true, ...(await response.json()) }
  } catch {
    return { running: false }
  }
}

// ------------------------------------------------------------------------- //
// Score disputes (user side)
// ------------------------------------------------------------------------- //
export async function createAppeal(scanId, reason, evidenceUrl) {
  const response = await fetch(`${API_BASE}/appeals`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ scan_id: scanId, reason, evidence_url: evidenceUrl || null }),
  })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

export async function getMyAppeals() {
  const response = await fetch(`${API_BASE}/appeals/mine`, { headers: authHeaders() })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

// ------------------------------------------------------------------------- //
// Admin console. Every one of these is checked for the admin role on the
// server — the frontend only decides what to show, never what's allowed.
// ------------------------------------------------------------------------- //
function toQuery(params = {}) {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, v)
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

async function adminGet(path, params) {
  const response = await fetch(`${API_BASE}/admin${path}${toQuery(params)}`, { headers: authHeaders() })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

async function adminPost(path, body = {}) {
  const response = await fetch(`${API_BASE}/admin${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await parseErrorMessage(response))
  return response.json()
}

export const adminApi = {
  overview: () => adminGet('/overview'),
  users: (params) => adminGet('/users', params),
  user: (id) => adminGet(`/users/${id}`),
  suspendUser: (id, reason) => adminPost(`/users/${id}/suspend`, { reason }),
  reactivateUser: (id) => adminPost(`/users/${id}/reactivate`, {}),
  setRole: (id, role) => adminPost(`/users/${id}/role`, { role }),
  scans: (params) => adminGet('/scans', params),
  scan: (id) => adminGet(`/scans/${id}`),
  appeals: (status) => adminGet('/appeals', { status }),
  appeal: (id) => adminGet(`/appeals/${id}`),
  resolveAppeal: (id, body) => adminPost(`/appeals/${id}/resolve`, body),
  models: () => adminGet('/models'),
  health: () => adminGet('/health'),
  auditLog: (params) => adminGet('/audit-log', params),

  // A plain <a href> can't send the Authorization header, so the CSV is
  // fetched with it and handed to the browser as a download.
  async downloadFeedback() {
    const response = await fetch(`${API_BASE}/admin/feedback/export`, { headers: authHeaders() })
    if (!response.ok) throw new Error(await parseErrorMessage(response))
    const disposition = response.headers.get('content-disposition') || ''
    const match = disposition.match(/filename="([^"]+)"/)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = match ? match[1] : 'trustlens_feedback.csv'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

export async function getCurrentUser(token) {
  const response = await fetch(`${API_BASE}/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }

  return response.json()
}

// ------------------------------------------------------------------------- //
// Added 2026-09-28: the rest of the Web Dashboard (watchlist, brand, creator),
// Visual Analytics, and PDF/CSV export.
// ------------------------------------------------------------------------- //
async function jsonCall(path, { method = 'GET', body } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw httpError("Can't reach the TrustLens server. Make sure the backend is running, then try again.", 0)
  }
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  return response.json()
}

// A plain link can't carry the login header, so files are fetched with it
// and handed to the browser as a download.
async function downloadFile(path, fallbackName, { method = 'GET', body } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw httpError("Can't reach the TrustLens server.", 0)
  }
  if (!response.ok) throw httpError(await parseErrorMessage(response), response.status)
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = match ? match[1] : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Reports and exports
export const downloadScanPdf = (scanId) => downloadFile(`/reports/scan/${scanId}.pdf`, `trustlens_report_${scanId}.pdf`)
export const downloadComparePdf = (scanIds) =>
  downloadFile('/reports/compare.pdf', 'trustlens_comparison.pdf', { method: 'POST', body: { scan_ids: scanIds } })
export const downloadScansCsv = (scanIds = []) =>
  downloadFile(`/exports/scans.csv${scanIds.length ? `?ids=${scanIds.join(',')}` : ''}`, 'trustlens_scans.csv')

// Watchlist and alerts
export const watchlistApi = {
  list: () => jsonCall('/watchlist'),
  add: (username) => jsonCall('/watchlist', { method: 'POST', body: { username } }),
  remove: (id) => jsonCall(`/watchlist/${id}`, { method: 'DELETE' }),
  recheck: (id) => jsonCall(`/watchlist/${id}/recheck`, { method: 'POST' }),
  alerts: () => jsonCall('/alerts'),
  markAlertsRead: () => jsonCall('/alerts/read', { method: 'POST' }),
}
