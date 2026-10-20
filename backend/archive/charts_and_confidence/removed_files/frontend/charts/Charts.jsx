// Visual Analytics (scope §6.9): the charts shown on Results and Comparison.
// Built with Recharts, as the scope document specifies. Every chart:
//   - is drawn only from numbers the scan actually returned (nothing padded
//     or invented; a check that didn't apply is labelled "n/a", not drawn as 0
//     without saying so),
//   - has a plain-language summary under it (ChartCard),
//   - has a "View as table" toggle, so no value is only readable by hovering.
import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, Pie, PieChart,
  PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { MODULE_LABEL, MODULE_ORDER, SERIES_COLORS } from '../../lib/charting'
import './Charts.css'

const INK = '#2B1140'
const GRID = 'rgba(43, 17, 64, 0.12)'
const TONE = { ok: '#07805F', warn: '#9A6206', bad: '#C0321F' }
const BAND_FILL = { ok: '#BFEFE0', warn: '#FBE3B0', bad: '#FFD0C8' }


const axisTick = { fill: 'rgba(43, 17, 64, 0.66)', fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }
const tooltipStyle = {
  contentStyle: { borderRadius: 12, border: `2px solid ${INK}`, fontFamily: 'Archivo, sans-serif', fontSize: 13 },
  labelStyle: { fontWeight: 700, color: INK },
}

const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : n)

export function ChartCard({ title, eyebrow, summary, summarySource, table, children, className = '' }) {
  const [showTable, setShowTable] = useState(false)
  return (
    <figure className={`ch-card tl-card ${className}`}>
      <figcaption className="ch-head">
        {eyebrow && <span className="ch-eyebrow">{eyebrow}</span>}
        <strong>{title}</strong>
      </figcaption>
      <div className="ch-body">{showTable ? table : children}</div>
      {summary !== undefined && (
        <p className="ch-summary">
          {summary || <span className="ch-summary-wait">Writing a plain-language summary…</span>}
          {summary && summarySource && (
            <span className="ch-summary-src">
              {summarySource === 'gemini' ? 'Worded by Gemini from the numbers above' : 'Written from the numbers above'}
            </span>
          )}
        </p>
      )}
      {table && (
        <button type="button" className="ch-toggle" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
          {showTable ? 'View as chart' : 'View as table'}
        </button>
      )}
    </figure>
  )
}

function DataTable({ columns, rows }) {
  return (
    <div className="ch-table-wrap">
      <table className="ch-table">
        <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Bot-percentage gauge
// --------------------------------------------------------------------------- //
function gaugeTone(v) {
  return v >= 70 ? 'bad' : v >= 40 ? 'warn' : 'ok'
}

export function BotGauge({ value, summary, summarySource }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0))
  const tone = gaugeTone(v)
  const bands = [
    { name: 'Looks genuine (under 40%)', value: 40, tone: 'ok' },
    { name: 'Borderline (40–69%)', value: 30, tone: 'warn' },
    { name: 'Looks fake (70%+)', value: 30, tone: 'bad' },
  ]
  const needle = [{ value: v }, { value: 100 - v }]
  return (
    <ChartCard
      eyebrow="Account authenticity"
      title="Fake-account likelihood"
      summary={summary}
      summarySource={summarySource}
      table={<DataTable columns={['Measure', 'Value']} rows={[
        ['Fake-account likelihood', `${v}%`], ['Zone', bands.find((b) => b.tone === tone).name],
      ]} />}
    >
      <div className="ch-gauge">
        <ResponsiveContainer width="100%" height={190}>
          <PieChart>
            <Pie data={bands} dataKey="value" startAngle={180} endAngle={0} cx="50%" cy="88%"
              innerRadius="92%" outerRadius="108%" stroke="#FFFFFF" strokeWidth={2} isAnimationActive={false}>
              {bands.map((b) => <Cell key={b.tone} fill={BAND_FILL[b.tone]} />)}
            </Pie>
            <Pie data={needle} dataKey="value" startAngle={180} endAngle={0} cx="50%" cy="88%"
              innerRadius="62%" outerRadius="84%" stroke="none" cornerRadius={4}>
              <Cell fill={TONE[tone]} />
              <Cell fill="rgba(43, 17, 64, 0.07)" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="ch-gauge-value" style={{ color: TONE[tone] }}>
          <strong>{v}%</strong>
          <span>likely fake</span>
        </div>
      </div>
      <ul className="ch-legend" aria-hidden="true">
        {bands.map((b) => <li key={b.tone}><i style={{ background: BAND_FILL[b.tone] }} />{b.name}</li>)}
      </ul>
    </ChartCard>
  )
}

// --------------------------------------------------------------------------- //
// Module-by-module radar (one account, or several overlaid)
// --------------------------------------------------------------------------- //
// series: [{ name, moduleScores: {fake_follower: 97, ...} }]
function RadarPlot({ series }) {
  const applied = new Set(series.flatMap((s) => Object.keys(s.moduleScores || {})))
  const data = MODULE_ORDER.map((m) => {
    const row = { module: MODULE_LABEL[m] + (applied.has(m) ? '' : ' (n/a)') }
    series.forEach((s, i) => { row[`s${i}`] = s.moduleScores?.[m] ?? 0 })
    return row
  })
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} outerRadius="72%" margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
        <PolarGrid stroke={GRID} />
        <PolarAngleAxis dataKey="module" tick={{ ...axisTick, fill: INK }} />
        <PolarRadiusAxis domain={[0, 100]} tickCount={5} tick={{ ...axisTick, fontSize: 10 }} axisLine={false} angle={90} />
        {series.map((s, i) => (
          <Radar key={s.name} name={s.name} dataKey={`s${i}`} stroke={SERIES_COLORS[i % 4]} strokeWidth={2}
            fill={SERIES_COLORS[i % 4]} fillOpacity={series.length > 1 ? 0.08 : 0.16}
            dot={{ r: 4, fill: SERIES_COLORS[i % 4], stroke: '#FFFFFF', strokeWidth: 2 }} />
        ))}
        <Tooltip {...tooltipStyle} formatter={(v) => `${Math.round(v * 10) / 10} / 100`} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 13 }} />}
      </RadarChart>
    </ResponsiveContainer>
  )
}

function moduleTable(series) {
  return (
    <DataTable
      columns={['Check', ...series.map((s) => s.name)]}
      rows={MODULE_ORDER.map((m) => [MODULE_LABEL[m], ...series.map((s) =>
        s.moduleScores?.[m] === undefined ? 'did not apply' : `${Math.round(s.moduleScores[m] * 10) / 10} / 100`)])}
    />
  )
}

// Comparison page: several accounts overlaid, which is what a radar is good at.
export function ModuleRadar({ series, summary, summarySource, title = 'Score of each check' }) {
  return (
    <ChartCard eyebrow="Module breakdown" title={title} summary={summary} summarySource={summarySource}
      table={moduleTable(series)}>
      <RadarPlot series={series} />
      <p className="ch-note">A check marked n/a didn’t apply; it sits at the centre and adds nothing to the score.</p>
    </ChartCard>
  )
}

// Results page: one account, so a plain list reads faster than a radar. One
// row per check: its score, how much it counted, or why it didn't apply.
// The radar is one click away (the scope document names a radar chart).
function barTone(v) {
  return v >= 70 ? 'ok' : v >= 40 ? 'warn' : 'bad'
}

function whyNotApplied(m, result) {
  if (m === 'credential') {
    const claims = result.credential_analysis?.claims_found || []
    return claims.length
      ? `The bio claims ${claims.join(', ')}, but there’s no public register to check that against`
      : 'The bio doesn’t claim any qualification'
  }
  if (m === 'misinformation') return 'There was no bio or caption text to read'
  if (m === 'engagement') return 'Instagram returned no posts to measure'
  return 'It didn’t run on this scan'
}

export function ModuleBars({ result, summary, summarySource }) {
  const [asRadar, setAsRadar] = useState(false)
  const scores = result.trust_score.module_scores || {}
  const weights = result.trust_score.weights_used || {}
  const series = [{ name: `@${result.username}`, moduleScores: scores }]

  return (
    <ChartCard eyebrow="Module breakdown" title="Score of each check" summary={summary}
      summarySource={summarySource} table={moduleTable(series)}>
      {asRadar ? <RadarPlot series={series} /> : (
        <ul className="mb-list">
          {MODULE_ORDER.map((m) => {
            const score = scores[m]
            if (score === undefined) {
              return (
                <li key={m} className="is-off">
                  <div className="mb-top"><span>{MODULE_LABEL[m]}</span><span className="mb-off">didn’t apply</span></div>
                  <p className="mb-why">{whyNotApplied(m, result)}, so its weight went to the other checks.</p>
                </li>
              )
            }
            const tone = barTone(score)
            return (
              <li key={m}>
                <div className="mb-top">
                  <span>{MODULE_LABEL[m]}</span>
                  <span className={`mb-score mb-${tone}`}>{Math.round(score * 10) / 10}<small> /100</small></span>
                </div>
                <div className="mb-track">
                  <div className={`mb-fill mb-fill-${tone}`} style={{ width: `${Math.max(2, score)}%` }} />
                </div>
                <p className="mb-why">Counts for {weights[m]}% of the Trust Score</p>
              </li>
            )
          })}
        </ul>
      )}
      <button type="button" className="ch-toggle mb-switch" onClick={() => setAsRadar((v) => !v)}>
        {asRadar ? 'Show as a list' : 'Show as a radar'}
      </button>
    </ChartCard>
  )
}

// --------------------------------------------------------------------------- //
// Engagement trend: likes per recent post (comments in the table view — a
// second measure on a different scale gets its own axis nowhere, never two)
// --------------------------------------------------------------------------- //
export function EngagementTrend({ posts, summary, summarySource }) {
  const ordered = [...(posts || [])].reverse()   // API gives newest first
  const data = ordered.map((p, i) => ({
    post: `#${i + 1}`,
    likes: p.likes,
    comments: p.comments,
    date: p.taken_at ? new Date(p.taken_at * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : null,
  }))
  const sorted = [...data].map((d) => d.likes).sort((a, b) => a - b)
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0
  return (
    <ChartCard
      eyebrow="Engagement"
      title="Likes on each recent post"
      summary={summary}
      summarySource={summarySource}
      table={<DataTable columns={['Post (oldest first)', 'Date', 'Likes', 'Comments']}
        rows={data.map((d) => [d.post, d.date || 'n/a', fmt(d.likes), fmt(d.comments)])} />}
    >
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 16, right: 20, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="post" tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64}
            tickFormatter={(v) => (v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : v)} />
          <ReferenceLine y={median} stroke={INK} strokeDasharray="4 4" strokeOpacity={0.5}
            label={{ value: 'median', position: 'insideTopRight', fill: 'rgba(43,17,64,0.66)', fontSize: 11 }} />
          <Tooltip {...tooltipStyle} formatter={(v, n) => [fmt(v), n]} labelFormatter={(l, p) => p?.[0]?.payload?.date ? `${l} · ${p[0].payload.date}` : l} />
          <Line type="linear" dataKey="likes" name="Likes" stroke={SERIES_COLORS[3]} strokeWidth={2}
            dot={(props) => {
              const spike = median && props.payload.likes > 3 * median
              return <circle key={props.index} cx={props.cx} cy={props.cy} r={spike ? 6 : 4}
                fill={spike ? TONE.bad : SERIES_COLORS[3]} stroke="#FFFFFF" strokeWidth={2} />
            }} />
        </LineChart>
      </ResponsiveContainer>
      <p className="ch-note">Dashed line: this account’s median. Red dots: over 3× the median, the usual look of bought likes.</p>
    </ChartCard>
  )
}

// --------------------------------------------------------------------------- //
// Follower growth timeline (from TrustLens's own scans over time)
// --------------------------------------------------------------------------- //
export function FollowerTimeline({ timeline, summary, summarySource }) {
  const points = timeline?.points || []
  return (
    <ChartCard
      eyebrow="Follower growth"
      title="Followers over time"
      summary={summary}
      summarySource={summarySource}
      table={<DataTable columns={['Date', 'Followers', 'Change', 'Flag']}
        rows={points.map((p) => [p.date, fmt(p.followers),
          p.change_pct === undefined ? '' : `${p.change_pct > 0 ? '+' : ''}${p.change_pct}%`,
          p.anomaly ? `Jump of ${timeline.jump_threshold_pct}%+` : ''])} />}
    >
      {points.length < 2 ? (
        <div className="ch-empty">
          <strong>{points.length === 1 ? `${fmt(points[0].followers)} followers on ${points[0].date}` : 'No history yet'}</strong>
          <span>
            Instagram doesn’t share follower history with outside tools, so this timeline is built from TrustLens’s own
            scans of the account. It fills in as the account is scanned on different days (watching it does this for you).
          </span>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={points} margin={{ top: 16, right: 20, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="date" tick={axisTick} tickLine={false} axisLine={{ stroke: GRID }} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} width={70} domain={['auto', 'auto']}
              tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : v)} />
            <Tooltip {...tooltipStyle} formatter={(v) => [fmt(v), 'Followers']} />
            <Line type="linear" dataKey="followers" stroke={SERIES_COLORS[0]} strokeWidth={2}
              dot={(props) => (
                <circle key={props.index} cx={props.cx} cy={props.cy} r={props.payload.anomaly ? 7 : 4}
                  fill={props.payload.anomaly ? TONE.bad : SERIES_COLORS[0]} stroke="#FFFFFF" strokeWidth={2} />
              )} />
          </LineChart>
        </ResponsiveContainer>
      )}
      {points.length >= 2 && (
        <p className="ch-note">Red dots: a change of {timeline.jump_threshold_pct}% or more since the previous scan.</p>
      )}
    </ChartCard>
  )
}

// --------------------------------------------------------------------------- //
// Comparison bar chart
// --------------------------------------------------------------------------- //
// items: [{ name, score, tone }]
export function ScoreBars({ items, summary }) {
  return (
    <ChartCard
      eyebrow="Comparison"
      title="Trust Score of each account"
      summary={summary}
      table={<DataTable columns={['Account', 'Trust Score']} rows={items.map((i) => [i.name, `${i.score} / 100`])} />}
    >
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={items} margin={{ top: 24, right: 12, bottom: 4, left: 0 }} barCategoryGap="28%">
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={{ ...axisTick, fill: INK }} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis domain={[0, 100]} ticks={[0, 40, 70, 100]} tick={axisTick} tickLine={false} axisLine={false} width={36} />
          <ReferenceLine y={70} stroke={TONE.ok} strokeDasharray="4 4" />
          <ReferenceLine y={40} stroke={TONE.warn} strokeDasharray="4 4" />
          <Tooltip {...tooltipStyle} formatter={(v) => [`${v} / 100`, 'Trust Score']} cursor={{ fill: 'rgba(43,17,64,0.05)' }} />
          <Bar dataKey="score" radius={[4, 4, 0, 0]} stroke="#FFFFFF" strokeWidth={2}>
            {items.map((it, i) => <Cell key={it.name} fill={SERIES_COLORS[i % 4]} />)}
            <LabelList dataKey="score" position="top" style={{ fill: INK, fontWeight: 700, fontSize: 13 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="ch-note">Dashed lines: 70 and above is Trusted, under 40 is High Risk.</p>
    </ChartCard>
  )
}
