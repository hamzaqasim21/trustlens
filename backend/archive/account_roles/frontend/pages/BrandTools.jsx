import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import RoleGate from '../components/RoleGate'
import {
  analyzeProfileBulk, apiKeysApi, API_BASE_URL, downloadComparePdf, downloadScanPdf, downloadScansCsv,
} from '../api/trustlens'
import { useAuth } from '../context/AuthContext'
import { parseUsername } from '../lib/scanFlow'
import { toneFor } from '../lib/verdict'
import './BrandTools.css'

// Brand / agency dashboard (scope §10): "bulk analysis tools, Influencer
// Comparison Engine for side-by-side forensic reports, CSV and PDF export,
// and API access for integration into their own marketing platforms."
const BULK_MAX = 10
const PARALLEL = 2   // two at a time: quick, without flooding Instagram with requests

function splitUsernames(text) {
  return [...new Set(text.split(/[\s,;]+/).map((t) => t.trim()).filter(Boolean))]
}

function BulkAnalysis() {
  const [text, setText] = useState('')
  const [rows, setRows] = useState([])        // [{ username, status, result?, error? }]
  const [running, setRunning] = useState(false)
  const [selected, setSelected] = useState({})
  const [msg, setMsg] = useState('')

  async function run(e) {
    e.preventDefault()
    setMsg('')
    const raw = splitUsernames(text)
    const names = raw.map(parseUsername)
    const bad = raw.filter((_, i) => !names[i])
    if (!raw.length) { setMsg('Paste at least one username or profile link.'); return }
    if (bad.length) { setMsg(`These don't look like Instagram usernames: ${bad.join(', ')}`); return }
    if (names.length > BULK_MAX) { setMsg(`Up to ${BULK_MAX} accounts at a time.`); return }

    const list = names.map((u) => ({ username: u, status: 'waiting' }))
    setRows(list)
    setSelected({})
    setRunning(true)
    const update = (i, patch) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)))
    let next = 0
    async function worker() {
      while (next < list.length) {
        const i = next++
        update(i, { status: 'scanning' })
        try {
          update(i, { status: 'done', result: await analyzeProfileBulk(list[i].username) })
        } catch (err) {
          update(i, { status: 'failed', error: err.message })
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(PARALLEL, list.length) }, worker))
    setRunning(false)
  }

  const done = rows.filter((r) => r.status === 'done')
  const pickedIds = done.filter((r) => selected[r.username]).map((r) => r.result.scan_id)

  async function exportCsv(ids) {
    try { await downloadScansCsv(ids) } catch (err) { setMsg(err.message) }
  }
  async function comparePdf() {
    try { await downloadComparePdf(pickedIds) } catch (err) { setMsg(err.message) }
  }

  return (
    <div className="br-card tl-card tl-card-pad">
      <div className="br-card-head">
        <span className="tl-chip tl-chip-ink tl-chip-plain">Bulk analysis</span>
        <h2>Check a list of influencers</h2>
        <p className="tl-muted">
          Paste up to {BULK_MAX} usernames or profile links, one per line or separated by commas. Each is a full, real scan,
          saved to your history.
        </p>
      </div>
      <form className="br-bulk-form" onSubmit={run}>
        <textarea className="tl-textarea tl-input-mono" rows={5} value={text} disabled={running}
          onChange={(e) => { setText(e.target.value); setMsg('') }}
          placeholder={'natgeo\nhttps://www.instagram.com/nasa/\nsome_creator, another_creator'} aria-label="Usernames to analyse" />
        <div className="br-row">
          <button type="submit" className="tl-btn tl-btn-grad" disabled={running}>
            {running ? `Scanning… ${done.length + rows.filter((r) => r.status === 'failed').length} of ${rows.length}` : 'Analyse all'}
          </button>
          <span className="tl-hint">{splitUsernames(text).length} account(s) in the list</span>
        </div>
      </form>
      {msg && <p className="tl-alert tl-alert-bad" role="alert">{msg}</p>}

      {rows.length > 0 && (
        <>
          <div className="br-table-wrap">
            <table className="br-table">
              <thead>
                <tr>
                  <th scope="col"><span className="br-sr">Select</span></th>
                  <th scope="col">Account</th>
                  <th scope="col">Trust Score</th>
                  <th scope="col">Verdict</th>
                  <th scope="col">Confidence</th>
                  <th scope="col">Bot %</th>
                  <th scope="col">Misinfo flags</th>
                  <th scope="col">Engagement</th>
                  <th scope="col"><span className="br-sr">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const res = r.result
                  const tone = res ? toneFor(res.trust_score.verdict) : 'neutral'
                  const flags = res ? (res.misinformation_sources || []).filter((s) => s.status === 'success' && s.misinformation_flag).length : null
                  return (
                    <tr key={r.username}>
                      <td>
                        {res && (
                          <input type="checkbox" aria-label={`Select @${r.username}`} checked={Boolean(selected[r.username])}
                            onChange={(e) => setSelected((s) => ({ ...s, [r.username]: e.target.checked }))} />
                        )}
                      </td>
                      <th scope="row">@{r.username}</th>
                      {r.status === 'done' ? (
                        <>
                          <td><strong className={`br-score br-${tone}`}>{res.trust_score.trust_score}</strong></td>
                          <td><span className={`tl-chip tl-chip-${tone}`}>{res.confidence?.needs_review ? 'Needs review' : res.trust_score.verdict}</span></td>
                          <td>{res.confidence ? `${res.confidence.confidence}% ${res.confidence.label}` : 'n/a'}</td>
                          <td>{res.fake_follower_analysis.bot_percentage}%</td>
                          <td>{flags}</td>
                          <td>{res.engagement_analysis.engagement_score == null ? 'Not measured' : `${res.engagement_analysis.engagement_rate}% · ${res.engagement_analysis.status}`}</td>
                          <td className="br-acts">
                            <Link to={`/results?id=${res.scan_id}`} className="tl-link">Open</Link>
                            <button className="br-linkbtn" onClick={() => downloadScanPdf(res.scan_id).catch((e) => setMsg(e.message))}>PDF</button>
                          </td>
                        </>
                      ) : (
                        <td colSpan={7} className={`br-status br-status-${r.status}`}>
                          {r.status === 'waiting' && 'Waiting…'}
                          {r.status === 'scanning' && <><span className="tl-spinner br-spin" /> Scanning…</>}
                          {r.status === 'failed' && r.error}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {done.length > 0 && !running && (
            <div className="br-row">
              <button className="tl-btn tl-btn-ink tl-btn-sm" onClick={() => exportCsv(done.map((r) => r.result.scan_id))}>
                Export all as CSV
              </button>
              <button className="tl-btn tl-btn-outline tl-btn-sm" onClick={comparePdf} disabled={pickedIds.length < 2 || pickedIds.length > 4}>
                Comparison PDF of selected ({pickedIds.length})
              </button>
              <span className="tl-hint">Tick 2 to 4 accounts for a side-by-side PDF report.</span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ApiKeys() {
  const [data, setData] = useState({ items: [], daily_limit: 100 })
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState(null)
  const [msg, setMsg] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiKeysApi.list().then((d) => { if (!cancelled) setData(d) }).catch((e) => { if (!cancelled) setMsg(e.message) })
    return () => { cancelled = true }
  }, [])

  async function create(e) {
    e.preventDefault()
    setMsg('')
    try {
      const k = await apiKeysApi.create(name.trim() || 'API key')
      setFresh(k)
      setCopied(false)
      setName('')
      setData(await apiKeysApi.list())
    } catch (err) {
      setMsg(err.message)
    }
  }

  async function revoke(id) {
    try {
      await apiKeysApi.revoke(id)
      setData(await apiKeysApi.list())
      if (fresh?.id === id) setFresh(null)
    } catch (err) {
      setMsg(err.message)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(fresh.key)
      setCopied(true)
    } catch {
      setMsg('Copy failed. Select the key and copy it by hand.')
    }
  }

  const example = fresh?.key || 'YOUR_API_KEY'
  return (
    <div className="br-card tl-card tl-card-pad">
      <div className="br-card-head">
        <span className="tl-chip tl-chip-ink tl-chip-plain">API access</span>
        <h2>Use TrustLens from your own tools</h2>
        <p className="tl-muted">
          Send a username, get back the same full result the website shows. Up to {data.daily_limit} API scans a day.
          Keys are stored only as a hash, so each one is shown once, when you create it.
        </p>
      </div>

      <form className="br-row" onSubmit={create}>
        <input className="tl-input br-keyname" value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
          placeholder="Key name, e.g. Campaign CRM" aria-label="New key name" />
        <button type="submit" className="tl-btn tl-btn-grad">Create key</button>
      </form>
      {msg && <p className="tl-alert tl-alert-bad" role="alert">{msg}</p>}

      {fresh && (
        <div className="tl-alert tl-alert-ok br-fresh" role="status">
          <div>
            <strong>Copy this key now. It won’t be shown again.</strong>
            <code className="br-key">{fresh.key}</code>
          </div>
          <button className="tl-btn tl-btn-ink tl-btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
        </div>
      )}

      {data.items.length > 0 && (
        <ul className="br-keys">
          {data.items.map((k) => (
            <li key={k.id} className={k.revoked ? 'is-revoked' : ''}>
              <div>
                <strong>{k.name}</strong>
                <span className="tl-mono">{k.prefix}…</span>
              </div>
              <span className="tl-hint">
                {k.revoked ? 'Revoked' : k.last_used_at ? `Last used ${new Date(k.last_used_at + 'Z').toLocaleString()}` : 'Never used'}
              </span>
              {!k.revoked && <button className="br-linkbtn br-danger" onClick={() => revoke(k.id)}>Revoke</button>}
            </li>
          ))}
        </ul>
      )}

      <details className="br-docs">
        <summary>How to call it</summary>
        <p className="tl-hint">From a terminal (PowerShell):</p>
        <pre>{`Invoke-RestMethod -Method Post -Uri ${API_BASE_URL}/api/v1/analyze \`
  -Headers @{ "X-API-Key" = "${example}" } \`
  -ContentType "application/json" -Body '{"username": "natgeo"}'`}</pre>
        <p className="tl-hint">Or with curl:</p>
        <pre>{`curl -X POST ${API_BASE_URL}/api/v1/analyze \\
  -H "X-API-Key: ${example}" -H "Content-Type: application/json" \\
  -d '{"username": "natgeo"}'`}</pre>
        <p className="tl-hint">
          Returns the full result (trust_score, confidence, every module). Fetch a saved one again with
          GET <code>/api/v1/scans/&lt;scan_id&gt;</code>. Errors: 401 bad key, 404 no such account, 429 daily limit.
          Full reference: <a className="tl-link" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">{API_BASE_URL}/docs</a>
        </p>
      </details>
    </div>
  )
}

function BrandTools() {
  const { user, loading, signedOut } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to={signedOut ? '/' : '/login?next=/brand'} replace />

  return (
    <PageShell title="Brand tools" className="br-page">
      <section className="tl-pagehead">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap">
          <span className="tl-eyebrow">Brand / agency dashboard</span>
          <h1 className="tl-display tl-pagehead-title">Brand<br /><span className="tl-grad-text">tools.</span></h1>
          <p className="tl-lede tl-pagehead-lede">
            Vet a shortlist before you spend a campaign budget: check many accounts at once, compare them side by side, take
            the report to your team as a PDF or CSV, or plug TrustLens into your own software.
          </p>
        </div>
      </section>
      {user.account_type !== 'brand' ? (
        <RoleGate type="brand" what="Brand tools" />
      ) : (
        <section className="tl-band tl-band-tint">
          <div className="tl-wrap br-stack">
            <BulkAnalysis />
            <div className="br-two">
              <div className="br-card tl-card tl-card-pad">
                <div className="br-card-head">
                  <span className="tl-chip tl-chip-ink tl-chip-plain">Comparison engine</span>
                  <h2>Side by side, 2 to 4 accounts</h2>
                  <p className="tl-muted">Radar and bar charts, every metric in one table, and a PDF report to share.</p>
                </div>
                <Link to="/comparison" className="tl-btn tl-btn-outline">Open the comparison</Link>
              </div>
              <div className="br-card tl-card tl-card-pad">
                <div className="br-card-head">
                  <span className="tl-chip tl-chip-ink tl-chip-plain">Export</span>
                  <h2>Everything you’ve scanned</h2>
                  <p className="tl-muted">One CSV row per scan, with the score, confidence and every module’s numbers.</p>
                </div>
                <button className="tl-btn tl-btn-outline" onClick={() => downloadScansCsv().catch(() => {})}>Download all scans as CSV</button>
              </div>
            </div>
            <ApiKeys />
          </div>
        </section>
      )}
    </PageShell>
  )
}

export default BrandTools
