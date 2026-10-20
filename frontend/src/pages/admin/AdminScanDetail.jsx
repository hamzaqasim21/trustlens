import { Link, useParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { ModuleBreakdown, ScanFacts } from './AdminAppealDetail'
import { PageHeader, Card, VerdictPill, AppealStatusPill, ErrorBanner, EmptyState } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDateTime } from './adminFormat'

function MisinfoSources({ sources }) {
  if (!sources?.length) return <EmptyState title="No text was classified">This profile had no bio or captions to check.</EmptyState>
  return (
    <table className="adm-table adm-table-compact">
      <thead><tr><th>Source</th><th>Text</th><th>Model's call</th><th className="adm-num">Risk</th></tr></thead>
      <tbody>
        {sources.map((s, i) => (
          <tr key={i}>
            <td>{s.source}</td>
            <td className="adm-truncate" title={s.text_preview}>{s.text_preview || '—'}</td>
            <td>{s.status === 'success' ? String(s.primary_category).replace(/_/g, ' ') : s.status}</td>
            <td className="adm-num">{s.risk_score ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function AdminScanDetail() {
  const { id } = useParams()
  const { data, error, loading, reload } = useAdminResource(() => adminApi.scan(id), [id])

  if (!data) {
    return (
      <div>
        <Link to="/admin/scans" className="adm-back">← All scans</Link>
        <ErrorBanner message={error} onRetry={reload} />
        {loading && <p className="adm-muted">Loading…</p>}
      </div>
    )
  }

  const s = data.scan
  const r = data.result

  return (
    <div>
      <Link to="/admin/scans" className="adm-back">← All scans</Link>
      <PageHeader
        eyebrow={`SCAN #${s.id}`}
        title={`@${s.username}`}
        subtitle={`Scanned ${formatDateTime(s.scanned_at)} · ${data.owner ? `by ${data.owner.email}` : 'anonymously'}`}
        actions={<VerdictPill verdict={s.corrected_verdict || s.verdict} />}
      />

      <div className="adm-grid-2 adm-grid-wide-left">
        <div className="adm-stack">
          <Card eyebrow="PROFILE" title="What was measured">
            {r ? <ScanFacts result={r} /> : <p className="adm-muted">The full result wasn't stored for this scan.</p>}
          </Card>
          <Card eyebrow="TRUST SCORE" title="How the score was built">
            <ModuleBreakdown result={r} />
          </Card>
          <Card eyebrow="MISINFORMATION" title="Every text the classifier read">
            <MisinfoSources sources={r?.misinformation_sources} />
          </Card>
        </div>

        <div className="adm-stack">
          <Card eyebrow="RESULT" title="Score">
            <div className="adm-score-hero">
              <span className="adm-score-hero-value">{s.corrected_trust_score ?? s.trust_score}</span>
              <span className="adm-muted">/ 100</span>
            </div>
            {s.corrected_trust_score !== null && (
              <p className="adm-footnote">
                Corrected after a report. The models originally scored this {s.trust_score} ({s.verdict}) — that original is kept on record.
              </p>
            )}
          </Card>
          <Card eyebrow="REPORT" title="Report status">
            {data.appeal_id ? (
              <dl className="adm-facts">
                <div><dt>Status</dt><dd><AppealStatusPill status={data.appeal_status} /></dd></div>
                <div><dt>Case</dt><dd><Link to={`/admin/appeals/${data.appeal_id}`} className="adm-link">Open report #{data.appeal_id} →</Link></dd></div>
              </dl>
            ) : (
              <p className="adm-muted">Nobody has reported this score.</p>
            )}
          </Card>
          {data.owner && (
            <Card eyebrow="RUN BY" title={data.owner.full_name}>
              <Link to={`/admin/users/${data.owner.id}`} className="adm-link">{data.owner.email} →</Link>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

export default AdminScanDetail
