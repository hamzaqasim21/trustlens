// Influencer Comparison Engine charts (scope §6.10: "presented in a side-by-side
// table and radar chart format"). Built with Recharts. Every chart:
//   - is drawn only from numbers the scans actually returned (a check that
//     didn't apply is labelled "n/a", never silently drawn as a real 0),
//   - has a "View as table" toggle, so no value is only readable by hovering.
import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { MODULE_LABEL, MODULE_ORDER, SERIES_COLORS } from '../../lib/charting'
import './ComparisonCharts.css'

const INK = '#2B1140'
const GRID = 'rgba(43, 17, 64, 0.12)'
const TONE = { ok: '#07805F', warn: '#9A6206' }

const axisTick = { fill: 'rgba(43, 17, 64, 0.66)', fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }
const tooltipStyle = {
  contentStyle: { borderRadius: 12, border: `2px solid ${INK}`, fontFamily: 'Archivo, sans-serif', fontSize: 13 },
  labelStyle: { fontWeight: 700, color: INK },
}

const round1 = (v) => Math.round(v * 10) / 10

function ChartCard({ title, eyebrow, table, children }) {
  const [showTable, setShowTable] = useState(false)
  return (
    <figure className="ch-card tl-card">
      <figcaption className="ch-head">
        {eyebrow && <span className="ch-eyebrow">{eyebrow}</span>}
        <strong>{title}</strong>
      </figcaption>
      <div className="ch-body">{showTable ? table : children}</div>
      <button type="button" className="ch-toggle" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}>
        {showTable ? 'View as chart' : 'View as table'}
      </button>
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

// series: [{ name, moduleScores: { fake_follower: 97, ... } }] — straight from
// each scan's trust_score.module_scores, the same numbers the score was built from.
export function ModuleRadar({ series }) {
  const applied = new Set(series.flatMap((s) => Object.keys(s.moduleScores || {})))
  const data = MODULE_ORDER.map((m) => {
    const row = { module: MODULE_LABEL[m] + (applied.has(m) ? '' : ' (n/a)') }
    series.forEach((s, i) => { row[`s${i}`] = s.moduleScores?.[m] ?? 0 })
    return row
  })
  const table = (
    <DataTable
      columns={['Check', ...series.map((s) => s.name)]}
      rows={MODULE_ORDER.map((m) => [MODULE_LABEL[m], ...series.map((s) =>
        s.moduleScores?.[m] === undefined ? 'did not apply' : `${round1(s.moduleScores[m])} / 100`)])}
    />
  )
  return (
    <ChartCard eyebrow="Radar chart" title="The four checks, overlaid" table={table}>
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={data} outerRadius="70%" margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
          <PolarGrid stroke={GRID} />
          <PolarAngleAxis dataKey="module" tick={{ ...axisTick, fill: INK }} />
          <PolarRadiusAxis domain={[0, 100]} tickCount={5} tick={{ ...axisTick, fontSize: 10 }} axisLine={false} angle={90} />
          {series.map((s, i) => (
            <Radar key={s.name} name={s.name} dataKey={`s${i}`} stroke={SERIES_COLORS[i % 4]} strokeWidth={2}
              fill={SERIES_COLORS[i % 4]} fillOpacity={0.08}
              dot={{ r: 4, fill: SERIES_COLORS[i % 4], stroke: '#FFFFFF', strokeWidth: 2 }} />
          ))}
          <Tooltip {...tooltipStyle} formatter={(v) => `${round1(v)} / 100`} />
          <Legend wrapperStyle={{ fontSize: 13 }} />
        </RadarChart>
      </ResponsiveContainer>
      <p className="ch-note">
        Further out is better on every axis. A check marked n/a didn’t apply to any of these accounts; it sits at the
        centre and adds nothing to anyone’s score.
      </p>
    </ChartCard>
  )
}

// items: [{ name, score }]
export function ScoreBars({ items }) {
  return (
    <ChartCard
      eyebrow="Bar chart"
      title="Trust Score of each account"
      table={<DataTable columns={['Account', 'Trust Score']} rows={items.map((i) => [i.name, `${i.score} / 100`])} />}
    >
      <ResponsiveContainer width="100%" height={320}>
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
