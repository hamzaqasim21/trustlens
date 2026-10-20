// Scope §10, normal users: "Can save accounts for ongoing monitoring and
// receive alerts when scores drop." Lives on the Dashboard.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { watchlistApi } from '../api/trustlens'
import { parseUsername, USERNAME_HELP } from '../lib/scanFlow'
import { formatDateTime, toneFor } from '../lib/verdict'
import './WatchlistPanel.css'

function Change({ value }) {
  if (value === null || value === undefined) return <span className="wl-change">no change yet</span>
  if (Math.abs(value) < 0.05) return <span className="wl-change">no change</span>
  const up = value > 0
  return <span className={`wl-change ${up ? 'is-up' : 'is-down'}`}>{up ? '▲' : '▼'} {Math.abs(value)} since watched</span>
}

function WatchlistPanel() {
  const [data, setData] = useState({ items: [], auto_recheck_hours: null, drop_points: 5 })
  const [alerts, setAlerts] = useState({ items: [], unread: 0 })
  const [loading, setLoading] = useState(true)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState({})
  const [msg, setMsg] = useState(null)

  const load = useCallback(async () => {
    const [w, a] = await Promise.all([watchlistApi.list(), watchlistApi.alerts()])
    setData(w)
    setAlerts(a)
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([watchlistApi.list(), watchlistApi.alerts()])
      .then(([w, a]) => { if (!cancelled) { setData(w); setAlerts(a) } })
      .catch((err) => { if (!cancelled) setMsg({ ok: false, text: err.message }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  async function add(e) {
    e.preventDefault()
    const u = parseUsername(input)
    if (!u) { setMsg({ ok: false, text: USERNAME_HELP }); return }
    setMsg(null)
    try {
      const entry = await watchlistApi.add(u)
      setInput('')
      await load()
      setMsg({ ok: true, text: entry.last_score == null
        ? `Watching @${entry.username}. Press Re-check to get its first score, or wait for the daily check.`
        : `Watching @${entry.username}, starting from your latest scan (${entry.last_score}).` })
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    }
  }

  async function recheck(entry) {
    setBusy((b) => ({ ...b, [entry.id]: 'recheck' }))
    setMsg(null)
    try {
      const r = await watchlistApi.recheck(entry.id)
      await load()
      if (r.error) setMsg({ ok: false, text: `@${entry.username}: ${r.error}` })
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy((b) => ({ ...b, [entry.id]: null }))
    }
  }

  async function remove(entry) {
    setBusy((b) => ({ ...b, [entry.id]: 'remove' }))
    try {
      await watchlistApi.remove(entry.id)
      await load()
    } catch (err) {
      setMsg({ ok: false, text: err.message })
    } finally {
      setBusy((b) => ({ ...b, [entry.id]: null }))
    }
  }

  async function markRead() {
    await watchlistApi.markAlertsRead()
    await load()
  }

  return (
    <section className="tl-band db-watch">
      <div className="tl-wrap wl-grid">
        <div className="wl-main">
          <span className="tl-eyebrow">Watchlist</span>
          <h2 className="tl-display db-sec-title">Keep an eye<br />on them.</h2>
          <p className="tl-lede wl-lede">
            Watched accounts are re-checked automatically
            {data.auto_recheck_hours ? ` once every ${data.auto_recheck_hours} hours` : ''}, and you can re-check any of
            them now. If a score drops by {data.drop_points} points or more, or falls into a worse band, you get an alert
            here{' '}and by email.
          </p>

          <form className="wl-add" onSubmit={add}>
            <div className="tl-scanbar">
              <span className="tl-scanbar-at" aria-hidden="true">@</span>
              <input aria-label="Instagram username to watch" placeholder="username_to_watch" value={input}
                onChange={(e) => { setInput(e.target.value); setMsg(null) }} autoComplete="off" spellCheck="false" />
              <button type="submit" className="tl-btn tl-btn-grad tl-btn-sm">Watch</button>
            </div>
          </form>
          {msg && <p className={`tl-alert ${msg.ok ? 'tl-alert-ok' : 'tl-alert-bad'}`} role="status">{msg.text}</p>}

          {loading ? (
            <div className="wl-loading"><span className="tl-spinner" /></div>
          ) : data.items.length === 0 ? (
            <div className="tl-empty wl-empty">
              <h3>Nothing watched yet</h3>
              <p>Add an account above, or press “Watch this account” on any scan result.</p>
            </div>
          ) : (
            <ul className="wl-list">
              {data.items.map((e) => {
                const tone = e.last_verdict ? toneFor(e.last_verdict) : 'neutral'
                return (
                  <li key={e.id} className="wl-row tl-card">
                    <div className="wl-who">
                      <strong>@{e.username}</strong>
                      <span>
                        {e.last_checked_at ? `Checked ${formatDateTime(e.last_checked_at)}` : 'Not checked yet'}
                        {e.last_error && <em className="wl-err"> · last check failed: {e.last_error}</em>}
                      </span>
                    </div>
                    <div className="wl-score">
                      {e.last_score != null ? (
                        <>
                          <span className={`wl-num wl-${tone}`}>{e.last_score}</span>
                          <span className={`tl-chip tl-chip-${tone}`}>{e.last_verdict}</span>
                        </>
                      ) : <span className="wl-num">n/a</span>}
                      <Change value={e.change} />
                    </div>
                    <div className="wl-actions">
                      {e.last_scan_id && <Link className="tl-btn tl-btn-soft tl-btn-sm" to={`/results?id=${e.last_scan_id}`}>Open</Link>}
                      <button className="tl-btn tl-btn-outline tl-btn-sm" onClick={() => recheck(e)} disabled={Boolean(busy[e.id])}>
                        {busy[e.id] === 'recheck' ? 'Checking…' : 'Re-check now'}
                      </button>
                      <button className="wl-remove" onClick={() => remove(e)} disabled={Boolean(busy[e.id])}>Remove</button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <aside className="wl-alerts tl-card tl-card-pad" aria-labelledby="wl-alerts-title">
          <div className="wl-alerts-head">
            <h3 id="wl-alerts-title">Alerts {alerts.unread > 0 && <span className="wl-badge">{alerts.unread} new</span>}</h3>
            {alerts.unread > 0 && <button className="wl-remove" onClick={markRead}>Mark all read</button>}
          </div>
          {alerts.items.length === 0 ? (
            <p className="tl-muted wl-alerts-empty">No score drops so far. Alerts for watched accounts appear here.</p>
          ) : (
            <ul className="wl-alert-list">
              {alerts.items.map((a) => (
                <li key={a.id} className={a.read ? '' : 'is-new'}>
                  <div>
                    <strong>@{a.username}</strong> dropped from {a.old_score} to <strong className="wl-bad">{a.new_score}</strong>
                    {a.old_verdict !== a.new_verdict && <> ({a.old_verdict} → {a.new_verdict})</>}
                  </div>
                  <span>
                    {formatDateTime(a.created_at)}{a.emailed ? ' · emailed' : ''}
                    {a.scan_id && <> · <Link to={`/results?id=${a.scan_id}`}>see the scan</Link></>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </section>
  )
}

export default WatchlistPanel
