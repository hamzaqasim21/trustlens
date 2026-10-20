import { useEffect, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import ScoreRing from '../components/site/ScoreRing'
import Reveal from '../components/site/Reveal'
import { ModuleRadar, ScoreBars } from '../components/charts/Charts'
import { analyzeProfile, downloadComparePdf, downloadScansCsv } from '../api/trustlens'
import { useAuth } from '../context/AuthContext'
import { parseUsername, USERNAME_HELP } from '../lib/scanFlow'
import { toneFor } from '../lib/verdict'
import { SERIES_COLORS } from '../lib/charting'
import './Comparison.css'

// Influencer Comparison Engine (scope §6.10): "two or more public influencer
// usernames ... side-by-side comparison across all forensic metrics ...
// Trust Score, bot percentage, misinformation flag count, engagement
// authenticity rating, and credential confidence score ... structured table
// and radar chart format, and can be exported as a PDF report."
// Up to four, so the table and the radar stay readable.
const MAX = 4

const scoreOf = (r) => r.trust_score.trust_score

function summarySentence(results) {
  const ranked = [...results].sort((a, b) => scoreOf(b) - scoreOf(a))
  const [best, next] = ranked
  const lead = Math.round((scoreOf(best) - scoreOf(next)) * 10) / 10
  if (lead < 5) {
    return results.length === 2
      ? `Both profiles score about the same (${scoreOf(results[0])} vs ${scoreOf(results[1])}). Neither stands out as clearly more trustworthy.`
      : `The top two, @${best.username} and @${next.username}, are within 5 points (${scoreOf(best)} vs ${scoreOf(next)}). Look at the rows below before choosing.`
  }
  return `@${best.username} scores highest (${scoreOf(best)}), ${lead} points ahead of @${next.username}.`
}

const misinfoTexts = (r) => (r.misinformation_sources || []).filter((s) => s.status === 'success')
const misinfoFlagCount = (r) => misinfoTexts(r).filter((s) => s.misinformation_flag).length

function engagementRating(r) {
  const e = r.engagement_analysis
  if (e.engagement_score === null || e.engagement_score === undefined) return 'Not measured'
  return `${e.status} · ${e.engagement_rate}% (normal ${e.benchmark}%)`
}

function credentialText(r) {
  const c = r.credential_analysis || {}
  if (!c.claims_found?.length) return 'No claims'
  if (c.confidence_score === null || c.confidence_score === undefined) return `${c.claims_found.join(', ')}: not checkable`
  return `${c.confidence_score}/100 (${c.claims_found.join(', ')})`
}

// The rows of the comparison table. `num` is used to highlight the best value
// (better: 'high' | 'low'); rows without it are shown without a winner.
const ROWS = [
  { group: 'Overall' },
  { label: 'Trust Score', show: (r) => `${scoreOf(r)} / 100`, num: scoreOf, better: 'high' },
  { label: 'Verdict', show: (r) => (r.confidence?.needs_review ? `Needs review (${r.trust_score.verdict})` : r.trust_score.verdict) },
  { label: 'Confidence', show: (r) => (r.confidence ? `${r.confidence.confidence}% (${r.confidence.label})` : 'n/a'),
    num: (r) => r.confidence?.confidence, better: 'high' },
  { group: 'The four checks' },
  { label: 'Bot % (fake-account likelihood)', show: (r) => `${r.fake_follower_analysis.bot_percentage}%`,
    num: (r) => r.fake_follower_analysis.bot_percentage, better: 'low' },
  { label: 'Misinformation flags', show: (r) => `${misinfoFlagCount(r)} of ${misinfoTexts(r).length} texts`,
    num: misinfoFlagCount, better: 'low' },
  { label: 'Engagement authenticity', show: engagementRating,
    num: (r) => r.engagement_analysis.engagement_score, better: 'high' },
  { label: 'Comment authenticity', show: (r) => r.comment_authenticity?.verdict || 'n/a' },
  { label: 'Credential confidence', show: credentialText },
  { group: 'Profile' },
  { label: 'Followers', show: (r) => r.raw_profile_data.followers.toLocaleString() },
  { label: 'Posts', show: (r) => r.raw_profile_data.posts.toLocaleString() },
  { label: 'Verified by Instagram', show: (r) => (r.is_verified ? 'Yes' : 'No') },
]

function winnerIndex(row, results) {
  if (!row.num) return null
  const vals = results.map((r) => row.num(r))
  if (vals.some((v) => typeof v !== 'number')) return null
  const best = row.better === 'high' ? Math.max(...vals) : Math.min(...vals)
  const idx = vals.filter((v) => v === best).length === 1 ? vals.indexOf(best) : null
  return idx
}

function ComparisonTable({ results }) {
  return (
    <div className="cmp-table-wrap tl-card">
      <table className="cmp-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {results.map((r, i) => (
              <th scope="col" key={r.username}>
                <span className="cmp-swatch" style={{ background: SERIES_COLORS[i % 4] }} aria-hidden="true" />
                @{r.username}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => row.group ? (
            <tr key={row.group} className="cmp-table-group"><th colSpan={results.length + 1} scope="colgroup">{row.group}</th></tr>
          ) : (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {results.map((r, i) => {
                const win = winnerIndex(row, results) === i
                return <td key={r.username} className={win ? 'is-win' : ''}>{row.show(r)}{win && <span className="cmp-best"> best</span>}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProfileCard({ result, winner, color }) {
  const tone = toneFor(result.trust_score.verdict)
  return (
    <div className={`cmp-card tl-card ${winner ? 'is-winner' : ''}`}>
      {winner && <span className="cmp-winner tl-chip tl-chip-ink tl-chip-plain">Scores highest</span>}
      <div className="cmp-card-who">
        <span className="tl-avatar" style={{ background: color }} aria-hidden="true">{result.username.charAt(0).toUpperCase()}</span>
        <div>
          <strong>@{result.username}</strong>
          <span>{result.full_name || ' '}</span>
        </div>
      </div>
      <ScoreRing score={scoreOf(result)} tone={tone} size={170} />
      <span className={`tl-chip tl-chip-${tone}`}>{result.confidence?.needs_review ? 'Needs review' : result.trust_score.verdict}</span>
      <Link to={`/results?id=${result.scan_id ?? ''}`} state={{ result }} className="tl-btn tl-btn-outline tl-btn-sm">Open full result</Link>
    </div>
  )
}

function Comparison() {
  const { user, loading: authLoading, signedOut } = useAuth()
  const location = useLocation()
  const [inputs, setInputs] = useState([location.state?.a || '', ''])
  const [results, setResults] = useState(null)
  const [failed, setFailed] = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [exporting, setExporting] = useState('')

  useEffect(() => {
    if (!running) return
    const started = Date.now()
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250)
    return () => clearInterval(t)
  }, [running])

  if (authLoading) return null
  if (!user) return <Navigate to={signedOut ? '/' : '/login?next=/comparison'} replace />

  function setInput(i, v) {
    setInputs((arr) => arr.map((x, j) => (j === i ? v : x)))
    setError('')
  }

  async function handleCompare(e) {
    e.preventDefault()
    const names = inputs.map((v) => v.trim()).filter(Boolean)
    const parsed = names.map(parseUsername)
    if (names.length < 2) { setError('Enter at least two usernames to compare.'); return }
    if (parsed.some((p) => !p)) { setError(USERNAME_HELP); return }
    if (new Set(parsed).size !== parsed.length) { setError('The same account is in the list twice. Pick different ones.'); return }

    setRunning(true)
    setElapsed(0)
    setError('')
    setResults(null)
    setFailed([])
    // Every one is a real scan (saved to your history), all run at once. One
    // failing (a typo) doesn't throw away the others.
    const settled = await Promise.allSettled(parsed.map((u) => analyzeProfile(u)))
    const ok = settled.filter((s) => s.status === 'fulfilled').map((s) => s.value)
    const bad = settled.map((s, i) => (s.status === 'rejected' ? { username: parsed[i], message: s.reason?.message } : null)).filter(Boolean)
    setFailed(bad)
    if (ok.length >= 2) setResults(ok)
    else setError(bad.length ? `Couldn’t compare: ${bad.map((b) => `@${b.username}: ${b.message}`).join(' · ')}` : 'Something went wrong. Try again.')
    setRunning(false)
  }

  async function exportPdf() {
    setExporting('pdf')
    try { await downloadComparePdf(results.map((r) => r.scan_id)) } catch (err) { setError(err.message) } finally { setExporting('') }
  }
  async function exportCsv() {
    setExporting('csv')
    try { await downloadScansCsv(results.map((r) => r.scan_id)) } catch (err) { setError(err.message) } finally { setExporting('') }
  }

  const top = results ? [...results].sort((a, b) => scoreOf(b) - scoreOf(a)) : []
  const leaderLead = results ? scoreOf(top[0]) - scoreOf(top[1]) : 0
  const canExport = results && results.every((r) => r.scan_id)

  return (
    <PageShell title="Compare" className="cmp-page">
      <section className="cmp-head">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap cmp-head-inner">
          <span className="tl-eyebrow">Compare up to {MAX} profiles</span>
          <h1 className="tl-display cmp-title">This<br /><span className="tl-grad-text">or that?</span></h1>
          <p className="tl-lede">
            Choosing between creators for a campaign? Every account goes through the same four checks, side by side, with
            a radar chart, a bar chart and a PDF report you can share. Each one is a real scan, saved to your dashboard.
          </p>

          <form className="cmp-form-multi" onSubmit={handleCompare} noValidate>
            {inputs.map((v, i) => (
              <div className="cmp-input-row" key={i}>
                <span className="cmp-input-num" style={{ background: SERIES_COLORS[i % 4] }} aria-hidden="true">{i + 1}</span>
                <div className="tl-scanbar cmp-bar">
                  <span className="tl-scanbar-at" aria-hidden="true">@</span>
                  <input
                    aria-label={`Instagram username ${i + 1}`}
                    value={v}
                    onChange={(e) => setInput(i, e.target.value)}
                    placeholder={i === 0 ? 'first_username' : i === 1 ? 'second_username' : 'another_username'}
                    autoComplete="off"
                    spellCheck="false"
                    disabled={running}
                  />
                </div>
                {inputs.length > 2 && (
                  <button type="button" className="cmp-remove" onClick={() => setInputs((a) => a.filter((_, j) => j !== i))}
                    disabled={running} aria-label={`Remove username ${i + 1}`}>Remove</button>
                )}
              </div>
            ))}
            <div className="cmp-form-actions">
              {inputs.length < MAX && (
                <button type="button" className="tl-btn tl-btn-soft" onClick={() => setInputs((a) => [...a, ''])} disabled={running}>
                  + Add another account
                </button>
              )}
              <button type="submit" className="tl-btn tl-btn-grad tl-btn-lg" disabled={running}>
                {running ? 'Comparing…' : `Compare ${inputs.filter((x) => x.trim()).length || ''} accounts`}
              </button>
            </div>
          </form>
          {error && <p className="tl-alert tl-alert-bad cmp-error" role="alert">{error}</p>}
        </div>
      </section>

      <section className="tl-band tl-band-tint cmp-results">
        <div className="tl-wrap">
          {running && (
            <div className="cmp-running">
              <span className="tl-spinner" aria-hidden="true" />
              <div>
                <strong>Scanning {inputs.filter((x) => x.trim()).length} profiles at once</strong>
                <span className="tl-mono">{elapsed}s elapsed</span>
              </div>
            </div>
          )}

          {!running && !results && (
            <div className="tl-empty">
              <h3>Two to four usernames, one answer</h3>
              <p>Enter them above. Add a third or fourth with “Add another account”.</p>
            </div>
          )}

          {!running && results && (
            <>
              {failed.length > 0 && (
                <p className="tl-alert tl-alert-warn cmp-failed">
                  <span>Left out: {failed.map((f) => `@${f.username} (${f.message})`).join(' · ')}</span>
                </p>
              )}
              <Reveal>
                <div className="cmp-top">
                  <p className="cmp-summary">{summarySentence(results)}</p>
                  {canExport && (
                    <div className="cmp-exports">
                      <button className="tl-btn tl-btn-ink" onClick={exportPdf} disabled={Boolean(exporting)}>
                        {exporting === 'pdf' ? 'Preparing PDF…' : 'Download PDF report'}
                      </button>
                      <button className="tl-btn tl-btn-outline" onClick={exportCsv} disabled={Boolean(exporting)}>
                        {exporting === 'csv' ? 'Preparing CSV…' : 'Export CSV'}
                      </button>
                    </div>
                  )}
                </div>
              </Reveal>
              <div className={`cmp-cards cmp-cards-${results.length}`}>
                {results.map((r, i) => (
                  <Reveal key={r.username} delay={i * 90}>
                    <ProfileCard result={r} color={SERIES_COLORS[i % 4]} winner={leaderLead >= 5 && r === top[0]} />
                  </Reveal>
                ))}
              </div>
              <Reveal><ComparisonTable results={results} /></Reveal>
              <div className="ch-grid cmp-charts">
                <ScoreBars items={results.map((r) => ({ name: `@${r.username}`, score: scoreOf(r) }))} />
                <ModuleRadar title="The four checks, overlaid"
                  series={results.map((r) => ({ name: `@${r.username}`, moduleScores: r.trust_score.module_scores }))} />
              </div>
            </>
          )}
        </div>
      </section>
    </PageShell>
  )
}

export default Comparison
