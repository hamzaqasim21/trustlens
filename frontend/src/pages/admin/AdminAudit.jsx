import { Link, useSearchParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { PageHeader, Card, ErrorBanner, EmptyState, Pagination } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDateTime, actionLabel } from './adminFormat'

const MODULE_LABEL = {
  fake_follower: 'Account authenticity (fake-account model)',
  engagement: 'Engagement Analyzer',
  misinformation: 'Misinformation Classifier',
  credential: 'Credential Extractor',
  other: 'other',
}

// Renders the details of one entry as a readable sentence rather than raw
// JSON, since this is what a reviewer actually reads.
function Details({ entry }) {
  const d = entry.details || {}
  switch (entry.action) {
    case 'user.suspend':
      return <>{d.email} — “{d.reason}”</>
    case 'user.reactivate':
      return <>{d.email}{d.reason ? ` — “${d.reason}”` : ''}</>
    case 'user.role_change':
      return <>{d.email}: {d.from_role ? `${d.from_role} → ` : ''}{d.to_role}{d.via ? ` (via ${d.via})` : ''}</>
    case 'user.delete':
      return <>{d.email}{d.via ? ` (via ${d.via})` : ''}</>
    case 'appeal.resolve':
      return (
        <>
          {d.decision} report on @{d.username}
          {d.decision === 'upheld' && ` — score ${d.original_score} → ${d.corrected_score}, at fault: ${MODULE_LABEL[d.module_at_fault] || d.module_at_fault}`}
          {d.within_sla === false && ' — after the 48-hour deadline'}
        </>
      )
    case 'feedback.export':
      return <>{d.rows} upheld {d.rows === 1 ? 'case' : 'cases'} exported</>
    default:
      return <code>{JSON.stringify(d)}</code>
  }
}

function targetLink(entry) {
  if (entry.target_type === 'user' && entry.target_id) return `/admin/users/${entry.target_id}`
  if (entry.target_type === 'appeal' && entry.target_id) return `/admin/appeals/${entry.target_id}`
  return null
}

function AdminAudit() {
  const [params, setParams] = useSearchParams()
  const action = params.get('action') || 'all'
  const page = Number(params.get('page') || 1)

  const { data, error, loading, reload } = useAdminResource(
    () => adminApi.auditLog({ action, page, page_size: 50 }),
    [action, page],
  )

  function update(next) {
    const m = { action, page, ...next }
    const clean = {}
    if (m.action !== 'all') clean.action = m.action
    if (m.page > 1) clean.page = m.page
    setParams(clean)
  }

  return (
    <div className={loading && data ? 'adm-refreshing' : ''}>
      <PageHeader
        eyebrow="ACCOUNTABILITY"
        title="Audit log"
        subtitle="Every change an administrator makes is recorded here with who did it, when, and why. Entries can't be edited or deleted from the console."
      />

      <div className="adm-filterbar">
        <select className="adm-input adm-select" value={action} onChange={(e) => update({ action: e.target.value, page: 1 })} aria-label="Action type">
          <option value="all">All actions</option>
          {(data?.actions || []).map((a) => <option key={a} value={a}>{actionLabel(a)}</option>)}
        </select>
      </div>

      <ErrorBanner message={error} onRetry={reload} />

      <Card>
        {!data && loading && <p className="adm-muted">Loading…</p>}
        {data && data.items.length === 0 && (
          <EmptyState title="Nothing recorded yet">Suspensions, role changes, report decisions and data exports will appear here.</EmptyState>
        )}
        {data && data.items.length > 0 && (
          <>
            <table className="adm-table">
              <thead><tr><th>When</th><th>Administrator</th><th>Action</th><th>Details</th><th /></tr></thead>
              <tbody>
                {data.items.map((e) => {
                  const link = targetLink(e)
                  return (
                    <tr key={e.id}>
                      <td className="adm-nowrap">{formatDateTime(e.created_at)}</td>
                      <td>
                        <div>{e.admin}</div>
                        {e.admin_email && <div className="adm-cell-sub">{e.admin_email}</div>}
                      </td>
                      <td className="adm-cell-strong">{actionLabel(e.action)}</td>
                      <td className="adm-cell-wrap"><Details entry={e} /></td>
                      <td className="adm-num">{link && <Link to={link} className="adm-link">Open →</Link>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: p })} />
          </>
        )}
      </Card>
    </div>
  )
}

export default AdminAudit
