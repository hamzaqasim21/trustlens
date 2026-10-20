import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { useAuth } from '../../context/AuthContext'
import { AccountStatus } from './AdminUsers'
import {
  PageHeader, Card, Pill, VerdictPill, AppealStatusPill, ScoreCell, ErrorBanner, EmptyState, ConfirmDialog,
} from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDateTime, timeAgo, actionLabel } from './adminFormat'

function AdminUserDetail() {
  const { id } = useParams()
  const { user: me } = useAuth()
  const { data, error, loading, reload } = useAdminResource(() => adminApi.user(id), [id])
  const [dialog, setDialog] = useState(null)

  if (!data) {
    return (
      <div>
        <Link to="/admin/users" className="adm-back">← All users</Link>
        <ErrorBanner message={error} onRetry={reload} />
        {loading && <p className="adm-muted">Loading…</p>}
      </div>
    )
  }

  const u = data.user
  const isMe = u.id === me?.id

  // Each action is a confirm step; the server re-validates every rule
  // (not yourself, not another admin, reason required) regardless.
  const actions = {
    suspend: {
      title: `Suspend ${u.full_name}?`,
      body: <p>They'll be signed out on their next request and won't be able to log in. Their scans and reports are kept. You can reactivate them at any time.</p>,
      confirmLabel: 'Suspend account',
      danger: true,
      reasonLabel: 'Reason for suspending',
      reasonMin: 5,
      run: (reason) => adminApi.suspendUser(u.id, reason),
    },
    reactivate: {
      title: `Reactivate ${u.full_name}?`,
      body: <p>They'll be able to log in again straight away.</p>,
      confirmLabel: 'Reactivate account',
      run: () => adminApi.reactivateUser(u.id),
    },
    promote: {
      title: `Make ${u.full_name} an administrator?`,
      body: <p>They'll get full access to this console — users, reports, scans and the audit log. Only give this to people who run the platform.</p>,
      confirmLabel: 'Grant admin access',
      danger: true,
      run: () => adminApi.setRole(u.id, 'admin'),
    },
    demote: {
      title: `Remove admin access from ${u.full_name}?`,
      body: <p>Their account stays active as a normal user.</p>,
      confirmLabel: 'Remove admin access',
      run: () => adminApi.setRole(u.id, 'user'),
    },
  }

  const current = dialog ? actions[dialog] : null

  return (
    <div className={loading ? 'adm-refreshing' : ''}>
      <Link to="/admin/users" className="adm-back">← All users</Link>
      <PageHeader
        eyebrow={`USER #${u.id}`}
        title={u.full_name}
        subtitle={u.email}
        actions={<><AccountStatus user={u} /> {u.role === 'admin' && <Pill tone="blue">Admin</Pill>}</>}
      />
      <ErrorBanner message={error} onRetry={reload} />

      <div className="adm-grid-2 adm-grid-wide-left">
        <div className="adm-stack">
          <Card eyebrow="ACTIVITY" title={`Scans (${data.scans.length})`}>
            {data.scans.length === 0 ? (
              <EmptyState title="No scans on this account" />
            ) : (
              <table className="adm-table">
                <thead><tr><th>Account scanned</th><th className="adm-num">Score</th><th>Verdict</th><th>When</th></tr></thead>
                <tbody>
                  {data.scans.map((s) => (
                    <tr key={s.id} className="adm-row-link">
                      <td><Link to={`/admin/scans/${s.id}`} className="adm-row-anchor adm-cell-strong">@{s.username}</Link></td>
                      <td className="adm-num"><ScoreCell score={s.trust_score} corrected={s.corrected_trust_score} /></td>
                      <td><VerdictPill verdict={s.corrected_verdict || s.verdict} /></td>
                      <td title={formatDateTime(s.scanned_at)}>{timeAgo(s.scanned_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card eyebrow="REPORTS FILED" title={`Reports (${data.appeals.length})`}>
            {data.appeals.length === 0 ? (
              <EmptyState title="No reports filed" />
            ) : (
              <table className="adm-table">
                <thead><tr><th>Account</th><th className="adm-num">Score</th><th>Status</th><th>Filed</th></tr></thead>
                <tbody>
                  {data.appeals.map((a) => (
                    <tr key={a.id} className="adm-row-link">
                      <td><Link to={`/admin/appeals/${a.id}`} className="adm-row-anchor adm-cell-strong">@{a.username}</Link></td>
                      <td className="adm-num"><ScoreCell score={a.original_score} corrected={a.corrected_trust_score} /></td>
                      <td><AppealStatusPill status={a.status} /></td>
                      <td>{timeAgo(a.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>

        <div className="adm-stack">
          <Card eyebrow="ACCOUNT" title="Details">
            <dl className="adm-facts">
              <div><dt>Joined</dt><dd>{formatDateTime(u.created_at)}</dd></div>
              <div><dt>Last login</dt><dd>{u.last_login_at ? formatDateTime(u.last_login_at) : 'Not recorded'}</dd></div>
              <div><dt>Email verified</dt><dd>{u.email_verified ? 'Yes' : 'No — signup never completed'}</dd></div>
              <div><dt>Role</dt><dd>{u.role === 'admin' ? 'Administrator' : 'User'}</dd></div>
            </dl>
          </Card>

          <Card eyebrow="MANAGE" title="Actions">
            {isMe ? (
              <div className="adm-notice">
                This is your own account. Admins can't suspend or demote themselves from the console, so nobody can lock the platform out of its last administrator by accident.
              </div>
            ) : (
              <div className="adm-action-list">
                {u.is_active ? (
                  <button
                    className="adm-btn adm-btn-danger-ghost"
                    onClick={() => setDialog('suspend')}
                    disabled={u.role === 'admin'}
                    title={u.role === 'admin' ? 'Remove admin access first' : undefined}
                  >
                    Suspend account
                  </button>
                ) : (
                  <button className="adm-btn adm-btn-ghost" onClick={() => setDialog('reactivate')}>Reactivate account</button>
                )}
                {u.role === 'admin' ? (
                  <button className="adm-btn adm-btn-ghost" onClick={() => setDialog('demote')}>Remove admin access</button>
                ) : (
                  <button
                    className="adm-btn adm-btn-ghost"
                    onClick={() => setDialog('promote')}
                    disabled={!u.email_verified || !u.is_active}
                    title={!u.email_verified || !u.is_active ? 'Only verified, active accounts can be admins' : undefined}
                  >
                    Make administrator
                  </button>
                )}
                {u.role === 'admin' && u.is_active && (
                  <p className="adm-footnote">An administrator can't be suspended directly — remove their admin access first.</p>
                )}
              </div>
            )}
          </Card>

          <Card eyebrow="AUDIT TRAIL" title="Admin actions on this account">
            {data.admin_history.length === 0 ? (
              <p className="adm-muted">None.</p>
            ) : (
              <ul className="adm-activity">
                {data.admin_history.map((h, i) => (
                  <li key={i}>
                    <span className="adm-activity-what">{actionLabel(h.action)}</span>
                    <span className="adm-muted">
                      by {h.admin}
                      {h.details?.reason ? ` — “${h.details.reason}”` : ''}
                      {h.details?.to_role ? ` — to ${h.details.to_role}` : ''}
                    </span>
                    <span className="adm-activity-when">{timeAgo(h.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(current)}
        title={current?.title}
        body={current?.body}
        confirmLabel={current?.confirmLabel}
        danger={current?.danger}
        reasonLabel={current?.reasonLabel}
        reasonMin={current?.reasonMin}
        onConfirm={async (reason) => {
          await current.run(reason)
          setDialog(null)
          reload()
        }}
        onCancel={() => setDialog(null)}
      />
    </div>
  )
}

export default AdminUserDetail
