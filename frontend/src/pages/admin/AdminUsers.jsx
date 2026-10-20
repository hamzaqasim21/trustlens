import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { PageHeader, Card, Pill, ErrorBanner, EmptyState, Pagination } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDate, timeAgo, formatNumber } from './adminFormat'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'verified', label: 'Verified' },
  { key: 'unverified', label: 'Unverified' },
  { key: 'suspended', label: 'Suspended' },
  { key: 'admins', label: 'Admins' },
]

export function AccountStatus({ user }) {
  if (!user.is_active) return <Pill tone="red">Suspended</Pill>
  if (!user.email_verified) return <Pill tone="amber">Email not verified</Pill>
  return <Pill tone="green">Active</Pill>
}

function AdminUsers() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || 'all'
  const page = Number(params.get('page') || 1)
  const search = params.get('search') || ''
  const [draft, setDraft] = useState(search)
  const [draftFor, setDraftFor] = useState(search)

  // If the URL's search changes from outside the box (back button, a link
  // from another page), follow it. Done during render, which is React's
  // recommended way to adjust state when an input changes.
  if (draftFor !== search) {
    setDraftFor(search)
    setDraft(search)
  }

  // Search as you type, but only after a short pause, so each keystroke
  // doesn't fire its own request.
  useEffect(() => {
    if (draft === search) return
    const t = setTimeout(() => update({ search: draft, page: 1 }), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  function update(next) {
    const merged = { status, search, page, ...next }
    const clean = {}
    if (merged.status && merged.status !== 'all') clean.status = merged.status
    if (merged.search) clean.search = merged.search
    if (merged.page > 1) clean.page = merged.page
    setParams(clean)
  }

  const { data, error, loading, reload } = useAdminResource(
    () => adminApi.users({ search, status, page, page_size: 25 }),
    [search, status, page],
  )

  return (
    <div className={loading && data ? 'adm-refreshing' : ''}>
      <PageHeader
        eyebrow="USER ACCOUNT MANAGEMENT"
        title="Users"
        subtitle={data ? `${formatNumber(data.total)} ${status === 'all' ? 'accounts' : 'matching accounts'}` : undefined}
      />

      <div className="adm-filterbar">
        <input
          className="adm-input adm-search"
          type="search"
          placeholder="Search name or email"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="Search users"
        />
        <div className="adm-segmented" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`adm-seg ${status === f.key ? 'adm-seg-active' : ''}`}
              onClick={() => update({ status: f.key, page: 1 })}
              aria-pressed={status === f.key}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner message={error} onRetry={reload} />

      <Card>
        {!data && loading && <p className="adm-muted">Loading…</p>}
        {data && data.items.length === 0 && (
          <EmptyState title="No accounts match">Try a different search or filter.</EmptyState>
        )}
        {data && data.items.length > 0 && (
          <>
            <table className="adm-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Role</th>
                  <th className="adm-num">Scans</th>
                  <th>Joined</th>
                  <th>Last login</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <span className="adm-cell-strong">{u.full_name}</span>
                      <span className="adm-cell-sub">{u.email}</span>
                    </td>
                    <td><AccountStatus user={u} /></td>
                    <td>{u.role === 'admin' ? <Pill tone="blue">Admin</Pill> : <span className="adm-muted">User</span>}</td>
                    <td className="adm-num">{u.scan_count}</td>
                    <td>{formatDate(u.created_at)}</td>
                    <td>
                      {u.last_login_at
                        ? timeAgo(u.last_login_at)
                        : <span className="adm-muted" title="Login times are recorded from when the admin console was added, so earlier logins don't appear.">Not recorded</span>}
                    </td>
                    <td className="adm-num">
                      <Link to={`/admin/users/${u.id}`} className="adm-btn adm-btn-ghost adm-btn-sm">View details</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: p })} />
          </>
        )}
      </Card>
    </div>
  )
}

export default AdminUsers
