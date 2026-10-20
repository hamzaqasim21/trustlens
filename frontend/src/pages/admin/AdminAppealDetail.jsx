import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { adminApi } from '../../api/trustlens'
import { useAuth } from '../../context/AuthContext'
import {
  PageHeader, Card, AppealStatusPill, SlaBadge, VerdictPill, ErrorBanner, ConfirmDialog,
} from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDateTime, formatNumber } from './adminFormat'

const MODULE_NAMES = {
  fake_follower: 'Account Authenticity (fake-account model)',
  engagement: 'Engagement Analyzer',
  misinformation: 'Misinformation Classifier',
  credential: 'Credential Extractor',
}

// Same boundaries as verdict_for() in backend/trust_score.py. This is only a
// preview while typing — the server recomputes the verdict itself.
function previewVerdict(score) {
  if (score >= 70) return 'Trusted'
  if (score >= 40) return 'Moderate Risk'
  return 'High Risk'
}

export function ModuleBreakdown({ result }) {
  const ts = result?.trust_score
  if (!ts?.module_scores) return <p className="adm-muted">No module breakdown was stored for this scan.</p>
  return (
    <table className="adm-table adm-table-compact">
      <thead><tr><th>Module</th><th className="adm-num">Its score</th><th className="adm-num">Weight</th></tr></thead>
      <tbody>
        {Object.entries(ts.module_scores).map(([key, score]) => (
          <tr key={key}>
            <td>{MODULE_NAMES[key] || key}</td>
            <td className="adm-num">{Math.round(score * 10) / 10}</td>
            <td className="adm-num">{ts.weights_used?.[key] ?? '—'}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ScanFacts({ result }) {
  if (!result) return null
  const ff = result.fake_follower_analysis || {}
  const eng = result.engagement_analysis || {}
  const mis = result.misinformation_analysis || {}
  const cred = result.credential_analysis || {}
  return (
    <dl className="adm-facts adm-facts-grid">
      <div><dt>Followers</dt><dd>{formatNumber(result.raw_profile_data?.followers)}</dd></div>
      <div><dt>Fake-account likelihood</dt><dd>{ff.bot_percentage ?? '—'}%</dd></div>
      <div>
        <dt>Engagement</dt>
        <dd>{eng.engagement_rate === null || eng.engagement_rate === undefined ? 'Not measured' : `${eng.engagement_rate}% · ${eng.status}`}</dd>
      </div>
      <div>
        <dt>Misinformation</dt>
        <dd>{mis.status === 'success' ? `${String(mis.primary_category).replace(/_/g, ' ')} (${Math.round((mis.confidence || 0) * 100)}%)` : 'not checked — no text'}</dd>
      </div>
      <div><dt>Credential claims</dt><dd>{cred.claims_found?.length ? cred.claims_found.join(', ') : 'none'}</dd></div>
      <div><dt>Verified on Instagram</dt><dd>{result.is_verified ? 'Yes' : 'No'}</dd></div>
    </dl>
  )
}

function DecisionForm({ appeal, onDecided }) {
  const [decision, setDecision] = useState('')
  const [score, setScore] = useState('')
  const [module, setModule] = useState('')
  const [note, setNote] = useState('')
  const [confirming, setConfirming] = useState(false)

  const scoreNum = score === '' ? null : Number(score)
  const scoreOk = scoreNum !== null && !Number.isNaN(scoreNum) && scoreNum >= 0 && scoreNum <= 100
  const valid = decision && note.trim().length >= 10 && (decision === 'rejected' || (scoreOk && module))

  async function submit() {
    await adminApi.resolveAppeal(appeal.id, {
      decision,
      note: note.trim(),
      corrected_trust_score: decision === 'upheld' ? scoreNum : undefined,
      module_at_fault: decision === 'upheld' ? module : undefined,
    })
    setConfirming(false)
    onDecided()
  }

  return (
    <>
      <div className="adm-decision">
        <fieldset className="adm-choice-group">
          <legend className="adm-field-label">Decision</legend>
          <label className={`adm-choice ${decision === 'upheld' ? 'adm-choice-on' : ''}`}>
            <input type="radio" name="decision" value="upheld" checked={decision === 'upheld'} onChange={() => setDecision('upheld')} />
            <span>
              <strong>Uphold</strong>
              <span className="adm-cell-sub">The evidence shows the score was wrong. Set the corrected score.</span>
            </span>
          </label>
          <label className={`adm-choice ${decision === 'rejected' ? 'adm-choice-on' : ''}`}>
            <input type="radio" name="decision" value="rejected" checked={decision === 'rejected'} onChange={() => setDecision('rejected')} />
            <span>
              <strong>Reject</strong>
              <span className="adm-cell-sub">The original score stands.</span>
            </span>
          </label>
        </fieldset>

        {decision === 'upheld' && (
          <div className="adm-field-row">
            <label className="adm-field">
              <span className="adm-field-label">Corrected score (0–100)</span>
              <input
                className="adm-input"
                type="number" min="0" max="100" step="0.1"
                value={score}
                onChange={(e) => setScore(e.target.value)}
              />
              {scoreOk && (
                <span className="adm-field-hint">
                  Will read as <VerdictPill verdict={previewVerdict(scoreNum)} /> (was {appeal.scan.trust_score})
                </span>
              )}
            </label>
            <label className="adm-field">
              <span className="adm-field-label">Which part got it wrong?</span>
              <select className="adm-input" value={module} onChange={(e) => setModule(e.target.value)}>
                <option value="">Choose…</option>
                {Object.entries(appeal.modules).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
              <span className="adm-field-hint">This labels the case for retraining.</span>
            </label>
          </div>
        )}

        <label className="adm-field">
          <span className="adm-field-label">Explanation for the user</span>
          <textarea
            className="adm-input adm-textarea"
            rows={4}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="The user sees this on their dashboard. Say what you checked and why you decided this way."
          />
          <span className="adm-field-hint">{note.trim().length < 10 ? `At least 10 characters (${note.trim().length} so far)` : 'Shown to the user and saved in the audit log.'}</span>
        </label>

        <button className="adm-btn adm-btn-primary" disabled={!valid} onClick={() => setConfirming(true)}>
          Record decision
        </button>
      </div>

      <ConfirmDialog
        open={confirming}
        title={decision === 'upheld' ? `Uphold and set the score to ${scoreNum}?` : 'Reject this report?'}
        body={
          decision === 'upheld'
            ? <p>The user's scan will show {scoreNum} ({previewVerdict(scoreNum)}) instead of {appeal.scan.trust_score}. The original score is kept on record. This can't be undone from the panel.</p>
            : <p>The original score of {appeal.scan.trust_score} stands and the user sees your explanation. This can't be undone from the panel.</p>
        }
        confirmLabel={decision === 'upheld' ? 'Uphold report' : 'Reject report'}
        onConfirm={submit}
        onCancel={() => setConfirming(false)}
      />
    </>
  )
}

function AdminAppealDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: appeal, error, loading, reload } = useAdminResource(() => adminApi.appeal(id), [id])

  if (!appeal) {
    return (
      <div>
        <Link to="/admin/appeals" className="adm-back">← All reports</Link>
        <ErrorBanner message={error} onRetry={reload} />
        {loading && <p className="adm-muted">Loading…</p>}
      </div>
    )
  }

  const isOwn = appeal.filed_by?.id === user?.id
  const scan = appeal.scan

  return (
    <div className={loading ? 'adm-refreshing' : ''}>
      <Link to="/admin/appeals" className="adm-back">← All reports</Link>
      <PageHeader
        eyebrow={`REPORT #${appeal.id}`}
        title={`@${scan?.username}`}
        subtitle={`Filed ${formatDateTime(appeal.created_at)} by ${appeal.filed_by?.full_name}`}
        actions={<><AppealStatusPill status={appeal.status} /> <SlaBadge sla={appeal.sla} /></>}
      />
      <ErrorBanner message={error} onRetry={reload} />

      <div className="adm-grid-2 adm-grid-wide-left">
        <div className="adm-stack">
          <Card eyebrow="THE USER'S CASE" title="Why they think the score is wrong">
            <blockquote className="adm-quote">{appeal.reason}</blockquote>
            <dl className="adm-facts">
              <div>
                <dt>Evidence</dt>
                <dd>
                  {appeal.evidence_url
                    ? <a href={appeal.evidence_url} target="_blank" rel="noopener noreferrer nofollow" className="adm-link adm-break">{appeal.evidence_url}</a>
                    : 'None provided'}
                </dd>
              </div>
              <div>
                <dt>Filed by</dt>
                <dd><Link to={`/admin/users/${appeal.filed_by?.id}`} className="adm-link">{appeal.filed_by?.email}</Link></dd>
              </div>
            </dl>
            {appeal.evidence_url && (
              <p className="adm-footnote">Evidence links are supplied by the user. They open in a new tab and are not verified by TrustLens.</p>
            )}
          </Card>

          <Card
            eyebrow="WHAT THE MODELS SAID"
            title={<>Original score {scan?.trust_score} <VerdictPill verdict={scan?.verdict} /></>}
            action={<Link to={`/admin/scans/${scan?.id}`} className="adm-link">Full scan →</Link>}
          >
            <ScanFacts result={appeal.result} />
            <h3 className="adm-subhead">How the score was built</h3>
            <ModuleBreakdown result={appeal.result} />
          </Card>
        </div>

        <Card eyebrow="DECISION" title={appeal.status === 'pending' ? 'Decide this report' : 'Decision recorded'}>
          {appeal.status === 'pending' && isOwn && (
            <div className="adm-notice">
              You filed this report yourself, so you can't decide it. Another administrator has to review it — that's what keeps a decision independent.
            </div>
          )}
          {appeal.status === 'pending' && !isOwn && <DecisionForm appeal={appeal} onDecided={reload} />}
          {appeal.status !== 'pending' && (
            <dl className="adm-facts">
              <div><dt>Outcome</dt><dd><AppealStatusPill status={appeal.status} /></dd></div>
              {appeal.status === 'upheld' && (
                <>
                  <div><dt>Score changed</dt><dd>{scan?.trust_score} → <strong>{appeal.corrected_trust_score}</strong> <VerdictPill verdict={scan?.corrected_verdict} /></dd></div>
                  <div><dt>Part at fault</dt><dd>{appeal.modules[appeal.module_at_fault] || appeal.module_at_fault}</dd></div>
                </>
              )}
              <div><dt>Decided by</dt><dd>{appeal.resolved_by?.full_name}</dd></div>
              <div><dt>Decided</dt><dd>{formatDateTime(appeal.resolved_at)}</dd></div>
              <div><dt>Within 48 hours</dt><dd>{appeal.sla?.resolved_within_sla ? 'Yes' : 'No'}</dd></div>
              <div className="adm-facts-full"><dt>Explanation sent to the user</dt><dd>{appeal.admin_note}</dd></div>
            </dl>
          )}
        </Card>
      </div>
    </div>
  )
}

export default AdminAppealDetail
