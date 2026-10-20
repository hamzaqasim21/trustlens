// Pieces added to the Results page on 2026-09-28:
//   ConfidenceBlock  - scope "Confidence Display" + "Requires Further Review"
//   VisualAnalytics  - scope §6.9 charts, each with a plain-language summary
//   ReportActions    - PDF report download + "Watch this account"
import { useEffect, useState } from 'react'
import { BotGauge, EngagementTrend, FollowerTimeline, ModuleBars } from './charts/Charts'
import { downloadScanPdf, explainCharts, getTimeline, watchlistApi } from '../api/trustlens'
import { MODULE_LABEL } from '../lib/charting'
import './ResultExtras.css'

const CONF_TONE = { High: 'ok', Medium: 'warn', Uncertain: 'bad' }

export function ConfidenceBlock({ confidence }) {
  const [open, setOpen] = useState(false)
  if (!confidence) return null
  const tone = CONF_TONE[confidence.label] || 'warn'
  return (
    <div className={`rx-conf rx-conf-${tone}`}>
      <div className="rx-conf-row">
        <span className="rx-conf-label tl-mono">Confidence</span>
        <strong>{confidence.confidence}%</strong>
        <span className={`tl-chip tl-chip-${tone}`}>{confidence.label}</span>
        <button type="button" className="rx-conf-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? 'Hide why' : 'Why?'}
        </button>
      </div>
      {confidence.uncertain && (
        <p className="rx-conf-warn">
          Below 60% confidence: treat this result as uncertain and don’t draw firm conclusions from it.
        </p>
      )}
      {open && (
        <div className="rx-conf-detail">
          <ul>
            {confidence.factors.map((f) => (
              <li key={f.module}>
                <strong>{MODULE_LABEL[f.module]}: {f.certainty}% sure.</strong> {f.note}
              </li>
            ))}
            {confidence.missing.map((m) => (
              <li key={m.module} className="rx-conf-missing">
                <strong>{MODULE_LABEL[m.module]}: missing.</strong> {m.note}
              </li>
            ))}
          </ul>
          <p>
            {confidence.confidence}% = how sure the checks were ({confidence.certainty}%) × how much of the evidence we
            could get ({confidence.coverage}%). This is a rule-based measure of certainty and missing data, not a
            statistical probability that the verdict is right.
          </p>
        </div>
      )}
    </div>
  )
}

export function ReviewNotice({ confidence }) {
  if (!confidence?.needs_review) return null
  return (
    <p className="tl-alert tl-alert-warn rx-review" role="status">
      <span>
        <strong>Requires further review.</strong> Scores between 35 and 55 are borderline, so TrustLens doesn’t give a firm
        verdict here. Read the breakdown below and decide for yourself.
      </span>
    </p>
  )
}

export function ReportActions({ result }) {
  const [pdfBusy, setPdfBusy] = useState(false)
  const [watch, setWatch] = useState({ loading: true, entry: null })
  const [msg, setMsg] = useState('')
  const username = result.username?.toLowerCase()

  useEffect(() => {
    let cancelled = false
    watchlistApi.list()
      .then((r) => { if (!cancelled) setWatch({ loading: false, entry: r.items.find((e) => e.username === username) || null }) })
      .catch(() => { if (!cancelled) setWatch({ loading: false, entry: null }) })
    return () => { cancelled = true }
  }, [username])

  async function pdf() {
    setPdfBusy(true)
    setMsg('')
    try {
      await downloadScanPdf(result.scan_id)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setPdfBusy(false)
    }
  }

  async function toggleWatch() {
    setMsg('')
    setWatch((w) => ({ ...w, loading: true }))
    try {
      if (watch.entry) {
        await watchlistApi.remove(watch.entry.id)
        setWatch({ loading: false, entry: null })
        setMsg(`Stopped watching @${result.username}.`)
      } else {
        const entry = await watchlistApi.add(result.username)
        setWatch({ loading: false, entry })
        setMsg(`Watching @${result.username}. You’ll get an alert if its score drops.`)
      }
    } catch (err) {
      setWatch((w) => ({ ...w, loading: false }))
      setMsg(err.message)
    }
  }

  return (
    <div className="rx-actions">
      {result.scan_id && (
        <button type="button" className="tl-btn tl-btn-ink tl-btn-sm" onClick={pdf} disabled={pdfBusy}>
          {pdfBusy ? 'Preparing PDF…' : 'Download PDF report'}
        </button>
      )}
      <button type="button" className="tl-btn tl-btn-outline tl-btn-sm" onClick={toggleWatch} disabled={watch.loading}
        aria-pressed={Boolean(watch.entry)}>
        {watch.entry ? 'Watching · stop' : 'Watch this account'}
      </button>
      {msg && <span className="rx-actions-msg" role="status">{msg}</span>}
    </div>
  )
}

export function VisualAnalytics({ result }) {
  const [timeline, setTimeline] = useState(null)
  const [explained, setExplained] = useState(null)
  const posts = result.engagement_data?.posts || []
  const hasPosts = posts.length > 0

  useEffect(() => {
    let cancelled = false
    getTimeline(result.username)
      .then((t) => { if (!cancelled) setTimeline(t) })
      .catch(() => { if (!cancelled) setTimeline({ points: [], anomalies: [], jump_threshold_pct: 10 }) })
    if (result.scan_id) {
      explainCharts(result.scan_id)
        .then((e) => { if (!cancelled) setExplained(e) })
        .catch(() => { if (!cancelled) setExplained({ summaries: {}, source: null }) })
    }
    return () => { cancelled = true }
  }, [result.username, result.scan_id])

  // undefined hides the summary box (no saved scan to explain); '' shows "writing…".
  const sum = (key) => (!result.scan_id ? undefined : explained ? explained.summaries?.[key] || null : '')
  // Each chart says who wrote its summary: Gemini, or the rule-based fallback.
  const src = (key) => explained?.sources?.[key] || explained?.source

  return (
    <section className="tl-band rx-visual">
      <div className="tl-wrap">
        <div className="rx-visual-head">
          <span className="tl-eyebrow">Visual analytics</span>
          <h2 className="tl-display rs-sec-title">The scan,<br />at a glance.</h2>
          <p className="tl-lede">
            Charts of the same numbers the score was built from. Each one has a short plain-language reading, and every
            chart can be switched to a table.
          </p>
        </div>
        <div className="ch-grid">
          <BotGauge value={result.fake_follower_analysis?.bot_percentage} summary={sum('gauge')} summarySource={src('gauge')} />
          <ModuleBars result={result} summary={sum('radar')} summarySource={src('radar')} />
          {hasPosts ? (
            <EngagementTrend posts={posts} summary={sum('trend')} summarySource={src('trend')} />
          ) : (
            <div className="ch-card tl-card">
              <div className="ch-head"><span className="ch-eyebrow">Engagement</span><strong>Likes on each recent post</strong></div>
              <div className="ch-empty">
                <strong>No per-post numbers for this scan</strong>
                <span>
                  {result.engagement_analysis?.engagement_score == null
                    ? 'No posts could be read from this account.'
                    : 'This scan was saved before per-post numbers were kept. Re-scan to see the trend.'}
                </span>
              </div>
            </div>
          )}
          {timeline ? (
            <FollowerTimeline timeline={timeline} summary={sum('timeline')} summarySource={src('timeline')} />
          ) : (
            <div className="ch-card tl-card"><div className="ch-empty"><span className="tl-spinner" /></div></div>
          )}
        </div>
      </div>
    </section>
  )
}
