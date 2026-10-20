import { Link, useSearchParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { PageHeader, Card, AppealStatusPill, SlaBadge, ErrorBanner, EmptyState } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { timeAgo, formatDateTime } from './adminFormat'

const TABS = [
  { key: 'pending', label: 'Awaiting review' },
  { key: 'upheld', label: 'Upheld' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

function AdminAppeals() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || 'pending'
  const { data, error, loading, reload } = useAdminResource(() => adminApi.appeals(status), [status])
  const items = data?.items || []

  return (
    <div className={loading && data ? 'adm-refreshing' : ''}>
      <PageHeader
        eyebrow="SCORE REPORT REVIEW"
        title="Score reports"
        subtitle="When someone thinks a Trust Score is wrong, they file a report from their results page. The scope document commits to reviewing every one within 48 hours."
      />

      <div className="adm-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={status === t.key}
            className={`adm-tab ${status === t.key ? 'adm-tab-active' : ''}`}
            onClick={() => setParams(t.key === 'pending' ? {} : { status: t.key })}
          >
            {t.label}
          </button>
        ))}
      </div>

      <ErrorBanner message={error} onRetry={reload} />

      <Card>
        {!data && loading && <p className="adm-muted">Loading…</p>}
        {data && items.length === 0 && (
          <EmptyState title={status === 'pending' ? 'Nothing waiting for review' : 'No reports here yet'}>
            {status === 'pending'
              ? 'New reports appear here the moment a user files one from their results page.'
              : 'Decided reports are kept here permanently, with who decided and why.'}
          </EmptyState>
        )}
        {items.length > 0 && (
          <table className="adm-table">
            <thead>
              <tr>
                <th>Account reported</th>
                <th>Filed by</th>
                <th className="adm-num">Original score</th>
                <th>Status</th>
                <th>{status === 'pending' ? 'Time to 48 h' : 'Review time'}</th>
                <th>Filed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className={a.sla?.overdue ? 'adm-row-alert' : ''}>
                  <td>
                    <div className="adm-cell-strong">@{a.scan?.username}</div>
                    <div className="adm-cell-sub adm-truncate" title={a.reason}>{a.reason}</div>
                  </td>
                  <td>
                    <div>{a.filed_by?.full_name}</div>
                    <div className="adm-cell-sub">{a.filed_by?.email}</div>
                  </td>
                  <td className="adm-num">
                    {a.scan?.trust_score}
                    {a.corrected_trust_score !== null && <span className="adm-cell-sub"> → {a.corrected_trust_score}</span>}
                  </td>
                  <td><AppealStatusPill status={a.status} /></td>
                  <td><SlaBadge sla={a.sla} /></td>
                  <td className="adm-nowrap" title={formatDateTime(a.created_at)}>{timeAgo(a.created_at)}</td>
                  <td className="adm-num">
                    <Link to={`/admin/appeals/${a.id}`} className="adm-btn adm-btn-ghost adm-btn-sm">
                      {a.status === 'pending' ? 'Review' : 'Open'}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {status === 'pending' && items.length > 0 && (
        <p className="adm-footnote">
          Oldest first — the case at the top is the one closest to breaking the 48-hour promise.
        </p>
      )}
    </div>
  )
}

export default AdminAppeals
