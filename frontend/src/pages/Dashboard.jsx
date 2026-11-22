import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import Reveal from '../components/site/Reveal'
import CountUp from '../components/CountUp'
import WatchlistPanel from '../components/WatchlistPanel'
import { getScanHistory, getMyAppeals, downloadScansCsv } from '../api/trustlens'
import { useAuth } from '../context/AuthContext'
import { parseScanTarget, scanPath, SCAN_HELP } from '../lib/scanFlow'
import { formatDate, formatDateTime, toneFor } from '../lib/verdict'
import './Dashboard.css'

// After an upheld report, the corrected score is what TrustLens now says
// about that account, so it's what the totals use. The original is still
// shown (struck through) on the row, so nothing is hidden.
function effective(scan) {
  if (scan.corrected_trust_score !== null && scan.corrected_trust_score !== undefined) {
    return { score: scan.corrected_trust_score, verdict: scan.corrected_verdict, corrected: true }
  }
  return { score: scan.trust_score, verdict: scan.verdict, corrected: false }
}

const APPEAL_LABEL = {
  pending: ['Under review', 'warn'],
  upheld: ['Upheld, score corrected', 'ok'],
  rejected: ['Not upheld', 'bad'],
}

const FILTERS = [
  ['all', 'All'],
  ['Trusted', 'Trusted'],
  ['Moderate Risk', 'Moderate'],
  ['High Risk', 'High risk'],
]

function QuickScan() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
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
    <form className="db-quick" onSubmit={submit} noValidate>
      <div className="tl-scanbar">
        <span className="tl-scanbar-at" aria-hidden="true">@</span>
        <input
          aria-label="Instagram username, profile link or reel link"
          value={value}
          onChange={(e) => { setValue(e.target.value); setError('') }}
          placeholder="Scan a new profile"
          autoComplete="off"
          spellCheck="false"
        />
        <button type="submit" className="tl-btn tl-btn-grad">Scan</button>
      </div>
      {error && <p className="db-error" role="alert">{error}</p>}
    </form>
  )
}

function Dashboard() {
  const { user, loading: authLoading, signedOut } = useAuth()
  const [scans, setScans] = useState([])
  const [appeals, setAppeals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  useEffect(() => {
    if (!user) return
    let cancelled = false
    Promise.all([getScanHistory(100), getMyAppeals()])
      .then(([s, a]) => { if (!cancelled) { setScans(s); setAppeals(a) } })
      .catch((err) => { if (!cancelled) setError(err.message || 'Could not load your scan history.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [user])

  const counts = useMemo(() => {
    const c = { all: scans.length, Trusted: 0, 'Moderate Risk': 0, 'High Risk': 0 }
    scans.forEach((s) => { const v = effective(s).verdict; if (v in c) c[v] += 1 })
    return c
  }, [scans])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/^@/, '')
    return scans.filter((s) => {
      if (filter !== 'all' && effective(s).verdict !== filter) return false
      if (q && !s.username.toLowerCase().includes(q) && !(s.full_name || '').toLowerCase().includes(q)) return false
      return true
    })
  }, [scans, filter, query])

  if (authLoading) return null
  if (!user) return <Navigate to={signedOut ? '/' : '/login?next=/dashboard'} replace />

  const total = scans.length
  const avg = total ? scans.reduce((sum, s) => sum + effective(s).score, 0) / total : 0
  const openDisputes = appeals.filter((a) => a.status === 'pending').length
  const firstName = user.full_name?.split(' ')[0] || 'there'

  return (
    <PageShell title="Dashboard" className="db-page">
      <section className="db-head">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap db-head-grid">
          <div>
            <span className="tl-eyebrow">Your dashboard</span>
            <h1 className="tl-display db-title">Hi, <span className="tl-grad-text">{firstName}.</span></h1>
            <p className="tl-lede">Every scan you’ve run, what it found, and where your reports stand.</p>
          </div>
          <QuickScan />
        </div>

        <div className="tl-wrap">
          <div className="db-stats">
            <Reveal className="db-stat tl-card" delay={0}>
              <span className="db-stat-value"><CountUp value={total} /></span>
              <span className="db-stat-label">Scans run</span>
            </Reveal>
            <Reveal className="db-stat tl-card" delay={70}>
              <span className="db-stat-value db-ok"><CountUp value={counts.Trusted} /></span>
              <span className="db-stat-label">Trusted</span>
            </Reveal>
            <Reveal className="db-stat tl-card" delay={140}>
              <span className="db-stat-value db-bad"><CountUp value={counts['High Risk']} /></span>
              <span className="db-stat-label">Flagged high risk</span>
            </Reveal>
            <Reveal className="db-stat tl-card" delay={210}>
              <span className="db-stat-value tl-grad-text">{total ? <CountUp value={avg} decimals={1} /> : 'n/a'}</span>
              <span className="db-stat-label">Average Trust Score</span>
            </Reveal>
            <Reveal className="db-stat tl-card" delay={280}>
              <span className="db-stat-value"><CountUp value={openDisputes} /></span>
              <span className="db-stat-label">Reports under review</span>
            </Reveal>
          </div>
        </div>
      </section>

      <WatchlistPanel />

      <section className="tl-band tl-band-tint db-history">
        <div className="tl-wrap">
          <div className="db-toolbar">
            <h2 className="tl-display db-sec-title">Scan history</h2>
            {scans.length > 0 && (
              <button type="button" className="tl-btn tl-btn-outline tl-btn-sm db-history-export"
                onClick={() => downloadScansCsv().catch((err) => setError(err.message))}>
                Export all as CSV
              </button>
            )}
            <div className="db-controls">
              <div className="db-filters" role="group" aria-label="Filter by verdict">
                {FILTERS.map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className={`db-filter ${filter === key ? 'is-on' : ''}`}
                    aria-pressed={filter === key}
                    onClick={() => setFilter(key)}
                  >
                    {label} <span className="tl-mono">{counts[key] ?? 0}</span>
                  </button>
                ))}
              </div>
              <input
                className="tl-input db-search"
                type="search"
                placeholder="Search @username"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search your scans"
              />
            </div>
          </div>

          {loading && <div className="db-skeletons">{[0, 1, 2].map((i) => <div key={i} className="db-skel" />)}</div>}
          {!loading && error && <p className="tl-alert tl-alert-bad">{error}</p>}

          {!loading && !error && total === 0 && (
            <div className="tl-empty">
              <h3>No scans yet</h3>
              <p>Scan any public Instagram account and the result lands here, so you can reopen it or report it later.</p>
              <Link to="/scan" className="tl-btn tl-btn-grad">Run your first scan</Link>
            </div>
          )}

          {!loading && !error && total > 0 && visible.length === 0 && (
            <div className="tl-empty">
              <h3>Nothing matches</h3>
              <p>No scans fit that filter and search. Try clearing one of them.</p>
              <button className="tl-btn tl-btn-outline" onClick={() => { setFilter('all'); setQuery('') }}>Clear filters</button>
            </div>
          )}

          {!loading && !error && visible.length > 0 && (
            <ul className="db-list">
              {visible.map((scan, i) => {
                const eff = effective(scan)
                const tone = toneFor(eff.verdict)
                const appeal = scan.appeal_status ? APPEAL_LABEL[scan.appeal_status] : null
                return (
                  <Reveal as="li" key={scan.id} delay={Math.min(i, 8) * 40}>
                    <Link to={`/results?id=${scan.id}`} className={`db-row tl-card tl-card-hover db-tone-${tone}`}>
                      <span className="tl-avatar" aria-hidden="true">{scan.username.charAt(0).toUpperCase()}</span>
                      <span className="db-row-who">
                        <strong>@{scan.username}</strong>
                        <span>{scan.full_name || ' '}</span>
                      </span>
                      <span className="db-row-when tl-mono">{formatDate(scan.scanned_at)}</span>
                      <span className="db-row-flags">
                        {appeal && <span className={`tl-chip tl-chip-${appeal[1]}`}>Reported · {appeal[0]}</span>}
                        {scan.misinformation_flag && <span className="tl-chip tl-chip-bad tl-chip-plain">Misinfo flagged</span>}
                      </span>
                      <span className={`tl-chip tl-chip-${tone}`}>{eff.verdict}</span>
                      <span className="db-row-score">
                        {eff.corrected && <s className="tl-mono" title="Original score before your report was upheld">{scan.trust_score}</s>}
                        <span className="db-score-pill">{eff.score}</span>
                      </span>
                      <span className="db-row-go" aria-hidden="true">→</span>
                    </Link>
                  </Reveal>
                )
              })}
            </ul>
          )}
        </div>
      </section>

      {!loading && !error && appeals.length > 0 && (
        <section className="tl-band db-disputes">
          <div className="tl-wrap">
            <span className="tl-eyebrow">Reports</span>
            <h2 className="tl-display db-sec-title">What the<br />reviewers said.</h2>
            <div className="db-dispute-grid">
              {appeals.map((a) => {
                const [label, tone] = APPEAL_LABEL[a.status] || APPEAL_LABEL.pending
                return (
                  <Reveal key={a.id} className={`db-dispute tl-card tl-card-pad db-dtone-${tone}`}>
                    <div className="db-dispute-head">
                      <Link to={`/results?id=${a.scan_id}`} className="db-dispute-user">@{a.username}</Link>
                      <span className={`tl-chip tl-chip-${tone}`}>{label}</span>
                    </div>
                    <div className="db-dispute-block">
                      <span className="db-dispute-label">You said · {formatDateTime(a.created_at)}</span>
                      <p>{a.reason}</p>
                    </div>
                    <div className="db-dispute-block">
                      <span className="db-dispute-label">
                        {a.status === 'pending' ? 'Status' : 'Reviewer’s decision'}
                        {a.status === 'upheld' && ` · score ${a.original_score} → ${a.corrected_trust_score}`}
                      </span>
                      <p>{a.status === 'pending' ? 'A reviewer will decide within 48 hours of when you filed it.' : a.admin_note}</p>
                    </div>
                  </Reveal>
                )
              })}
            </div>
          </div>
        </section>
      )}
    </PageShell>
  )
}

export default Dashboard
