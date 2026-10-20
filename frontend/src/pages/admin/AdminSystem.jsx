import { useState } from 'react'
import { adminApi } from '../../api/trustlens'
import { PageHeader, Card, Pill, ErrorBanner } from './AdminUi'
import { useAdminResource } from './useAdminResource'
import { formatDateTime } from './adminFormat'

const MEASUREMENT = {
  live: { tone: 'green', text: 'Measured live, just now' },
  recorded: { tone: 'neutral', text: 'Recorded at training time' },
  none: { tone: 'neutral', text: 'No accuracy figure — not a trained model' },
}

function fileSize(bytes) {
  if (bytes === undefined || bytes === null) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(bytes > 100 * 1024 * 1024 ? 0 : 1)} MB`
}

function Metric({ label, value }) {
  if (value === undefined || value === null) return null
  return (
    <div className="adm-metric">
      <span className="adm-metric-value">{value}%</span>
      <span className="adm-metric-label">{label}</span>
    </div>
  )
}

function ModelCard({ m }) {
  const meas = MEASUREMENT[m.measurement] || MEASUREMENT.none
  const metrics = m.metrics
  return (
    <div className="adm-model">
      <div className="adm-model-head">
        <div>
          <h3 className="adm-model-name">{m.name}</h3>
          <div className="adm-model-kind">{m.kind}</div>
        </div>
        <Pill tone={m.is_ml ? 'blue' : 'neutral'}>{m.is_ml ? 'AI / ML' : 'Rule-based'}</Pill>
      </div>

      {metrics?.available && (
        <div className="adm-metrics">
          <Metric label="accuracy" value={metrics.accuracy} />
          <Metric label="precision" value={metrics.precision} />
          <Metric label="recall" value={metrics.recall} />
        </div>
      )}
      {metrics && metrics.available === false && (
        <div className="adm-error adm-error-inline">Could not evaluate: {metrics.error}</div>
      )}

      <div className="adm-model-foot">
        <Pill tone={meas.tone}>{meas.text}</Pill>
        {m.evaluated_on && <span className="adm-muted">on {m.evaluated_on}</span>}
      </div>
      <p className="adm-model-source">{m.source}</p>
      <div className="adm-model-artifact">
        {m.artifact?.present
          ? <>File present · {fileSize(m.artifact.size_bytes)} · changed {formatDateTime(m.artifact.modified_at)}</>
          : <span className="adm-text-danger">File missing</span>}
        {m.loaded_in_memory !== undefined && (
          <> · {m.loaded_in_memory ? 'loaded in memory' : 'loads on first use'}</>
        )}
      </div>
    </div>
  )
}

function AdminSystem() {
  const models = useAdminResource(() => adminApi.models())
  const health = useAdminResource(() => adminApi.health())
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  async function exportCsv() {
    setExporting(true)
    setExportError('')
    try {
      await adminApi.downloadFeedback()
    } catch (err) {
      setExportError(err.message)
    } finally {
      setExporting(false)
    }
  }

  const fb = models.data?.field_feedback
  const failing = health.data?.checks.filter((c) => !c.ok && !c.optional).length || 0

  return (
    <div>
      <PageHeader
        eyebrow="MODEL PERFORMANCE MONITORING"
        title="Models & system"
        subtitle="Which parts of TrustLens are machine learning and which are rules, how well each performs, and whether everything the platform depends on is working."
        actions={<button className="adm-btn adm-btn-ghost" onClick={() => { models.reload(); health.reload() }}>Re-check</button>}
      />

      <ErrorBanner message={models.error || health.error} onRetry={() => { models.reload(); health.reload() }} />

      <Card
        eyebrow="SYSTEM HEALTH"
        title={health.data ? (failing ? `${failing} ${failing === 1 ? 'problem needs' : 'problems need'} attention` : 'All required services are working') : 'Checking…'}
        action={health.data && <span className="adm-muted">checked {formatDateTime(health.data.checked_at)}</span>}
      >
        {health.data && (
          <ul className="adm-checks">
            {health.data.checks.map((c) => (
              <li key={c.name} className="adm-check">
                <span className={`adm-check-dot ${c.ok ? 'adm-ok' : c.optional ? 'adm-optional' : 'adm-bad'}`} aria-hidden="true" />
                <span className="adm-check-name">{c.name}{c.optional && <span className="adm-muted"> (optional)</span>}</span>
                <span className="adm-check-state">{c.ok ? 'OK' : c.optional ? 'Not running' : 'Problem'}</span>
                <span className="adm-check-detail">{c.detail}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="adm-footnote">Secrets are only ever checked for presence. Their values never leave the server.</p>
      </Card>

      <h2 className="adm-section-title">Models</h2>
      <div className="adm-models">
        {models.data?.models.map((m) => <ModelCard key={m.key} m={m} />)}
        {!models.data && models.loading && <p className="adm-muted">Evaluating…</p>}
      </div>

      <div className="adm-grid-2">
        <Card eyebrow="REAL-WORLD SIGNAL" title="What reports say about accuracy">
          {fb && (
            <>
              <div className="adm-metrics">
                <div className="adm-metric">
                  <span className="adm-metric-value">{fb.overturn_rate === null ? '—' : `${fb.overturn_rate}%`}</span>
                  <span className="adm-metric-label">of decided reports were upheld</span>
                </div>
                <div className="adm-metric">
                  <span className="adm-metric-value">{fb.disputes_resolved}</span>
                  <span className="adm-metric-label">reports decided</span>
                </div>
              </div>
              <p className="adm-card-text">
                Test-set accuracy says how a model did on a benchmark. This says how the whole product did on real
                cases a person looked at. It only counts reported scans, so it isn't an overall error rate — but every
                upheld case is a known mistake, attributed to the part that made it:
              </p>
              <table className="adm-table adm-table-compact">
                <thead><tr><th>Part at fault</th><th className="adm-num">Upheld cases</th></tr></thead>
                <tbody>
                  {Object.entries(fb.upheld_by_module).map(([k, n]) => (
                    <tr key={k}><td>{{
                      fake_follower: 'Account authenticity (fake-account model)',
                      engagement: 'Engagement Analyzer',
                      misinformation: 'Misinformation Classifier',
                      credential: 'Credential Extractor',
                      other: 'Other',
                    }[k] || k}</td><td className="adm-num">{n}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Card>

        <Card eyebrow="FEEDBACK LOOP" title="Retraining dataset">
          <p className="adm-card-text">
            The scope document says corrected scores should feed back into retraining. Every upheld report is
            stored with the original score, the corrected score and the part of the analysis that got it wrong.
            This exports them as a labelled CSV — the input a retraining run needs.
          </p>
          <p className="adm-card-text adm-muted">
            Retraining itself is a deliberate offline step. Nothing here changes a model automatically, so a bad
            batch of reports can never silently degrade the live system.
          </p>
          <button className="adm-btn adm-btn-primary" onClick={exportCsv} disabled={exporting}>
            {exporting ? 'Preparing…' : `Download CSV${fb ? ` (${fb.disputes_upheld} ${fb.disputes_upheld === 1 ? 'case' : 'cases'})` : ''}`}
          </button>
          {exportError && <div className="adm-error adm-error-inline">{exportError}</div>}
          <p className="adm-footnote">Each export is recorded in the audit log.</p>
        </Card>
      </div>
    </div>
  )
}

export default AdminSystem
