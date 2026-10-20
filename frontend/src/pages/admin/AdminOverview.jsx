import { Link } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { DailyColumns, VerdictBars } from './AdminCharts'
import { PageHeader, Card, StatTile, VerdictPill, ErrorBanner, EmptyState } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatNumber, timeAgo, actionLabel, formatDateTime } from './adminFormat'

function AdminOverview() {
  const { data, error, loading, reload } = useAdminResource(() => adminApi.overview())

  return (
    <div className={loading && data ? 'adm-refreshing' : ''}>
      <PageHeader
        eyebrow="PLATFORM-WIDE ANALYTICS"
        title="Overview"
        subtitle={data ? `Live from the database · updated ${formatDateTime(data.generated_at)}` : 'Live from the database'}
        actions={<button className="adm-btn adm-btn-ghost" onClick={reload} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>}
      />

      <ErrorBanner message={error} onRetry={reload} />
      {!data && loading && <p className="adm-muted">Loading…</p>}

      {data && (
        <>
          {data.appeals.overdue > 0 && (
            <Link to="/admin/appeals" className="adm-alert">
              <strong>{data.appeals.overdue} score {data.appeals.overdue === 1 ? 'report has' : 'reports have'} passed the 48-hour review promise.</strong>
              <span>Review now →</span>
            </Link>
          )}

          <div className="adm-stats">
            <StatTile
              label="Total users"
              value={formatNumber(data.users.total)}
              sub={`${data.users.verified} verified · ${data.users.new_last_7_days} new this week`}
            />
            <StatTile
              label="Scans run"
              value={formatNumber(data.scans.total)}
              sub={`${data.scans.today} today · ${data.scans.last_7_days} this week`}
            />
            <StatTile
              label="Average trust score"
              value={data.scans.average_trust_score ?? '—'}
              sub="across every scan ever run"
            />
            <StatTile
              label="Reports awaiting review"
              value={formatNumber(data.appeals.pending)}
              sub={data.appeals.overdue ? `${data.appeals.overdue} overdue` : 'none overdue'}
              tone={data.appeals.overdue ? 'danger' : data.appeals.pending ? 'warning' : undefined}
            />
          </div>

          <div className="adm-grid-2">
            <Card eyebrow="LAST 14 DAYS" title="Scans per day">
              <DailyColumns data={data.scans_per_day} unit="scans" ariaLabel="Scans per day for the last 14 days" />
            </Card>
            <Card eyebrow="LAST 14 DAYS" title="New sign-ups per day">
              <DailyColumns data={data.signups_per_day} unit="sign-ups" ariaLabel="New sign-ups per day for the last 14 days" />
            </Card>
          </div>

          <div className="adm-grid-2">
            <Card eyebrow="WHAT THE MODELS CONCLUDED" title="Scans by verdict">
              <VerdictBars verdicts={data.scans.verdicts} />
              <dl className="adm-facts">
                <div>
                  <dt>Misinformation flagged</dt>
                  <dd>{data.scans.misinformation_flag_rate === null ? '—' : `${data.scans.misinformation_flag_rate}% of scans with text`}</dd>
                </div>
                <div>
                  <dt>Run by signed-in users</dt>
                  <dd>{formatNumber(data.scans.by_logged_in_users)} of {formatNumber(data.scans.total)}</dd>
                </div>
                <div>
                  <dt>Reports decided</dt>
                  <dd>{data.appeals.upheld} upheld · {data.appeals.rejected} rejected</dd>
                </div>
              </dl>
            </Card>

            <Card eyebrow="MOST SCANNED" title="Accounts people check most" action={<Link to="/admin/scans" className="adm-link">All scans →</Link>}>
              {data.top_accounts.length === 0 ? (
                <EmptyState title="No scans yet" />
              ) : (
                <table className="adm-table">
                  <thead>
                    <tr><th>Account</th><th className="adm-num">Scans</th><th className="adm-num">Latest score</th><th>Verdict</th></tr>
                  </thead>
                  <tbody>
                    {data.top_accounts.map((a) => (
                      <tr key={a.username}>
                        <td><Link to={`/admin/scans?search=${encodeURIComponent(a.username)}`} className="adm-link">@{a.username}</Link></td>
                        <td className="adm-num">{a.scans}</td>
                        <td className="adm-num">{a.latest_score ?? '—'}</td>
                        <td><VerdictPill verdict={a.latest_verdict} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>

          <Card eyebrow="ACCOUNTABILITY" title="Recent admin activity" action={<Link to="/admin/audit" className="adm-link">Full audit log →</Link>}>
            {data.recent_activity.length === 0 ? (
              <EmptyState title="No admin actions yet">Suspensions, role changes and report decisions will be listed here.</EmptyState>
            ) : (
              <ul className="adm-activity">
                {data.recent_activity.map((a, i) => (
                  <li key={i}>
                    <span className="adm-activity-what">{actionLabel(a.action)}</span>
                    <span className="adm-muted">by {a.admin}</span>
                    <span className="adm-activity-when">{timeAgo(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

export default AdminOverview
