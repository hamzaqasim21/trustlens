import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import ScoreRing from '../components/site/ScoreRing'
import { getPublicBadge } from '../api/trustlens'
import { formatDate, toneFor } from '../lib/verdict'
import './BadgeVerify.css'

// Public page (no login) that the QR code / link on a Trust Badge
// certificate points to. It shows the record TrustLens holds, so a brand can
// tell a genuine certificate from an edited one.
function BadgeVerify() {
  const { code } = useParams()
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    getPublicBadge(code)
      .then((b) => { if (!cancelled) setState({ badge: b }) })
      .catch((err) => { if (!cancelled) setState({ error: err.message }) })
    return () => { cancelled = true }
  }, [code])

  const b = state.badge
  const status = !b ? null : b.valid ? ['Genuine and current', 'ok'] : b.revoked ? ['Revoked', 'bad'] : ['Genuine, but expired', 'warn']

  return (
    <PageShell title="Check a Trust Badge" className="bv-page">
      <section className="tl-band">
        <div className="tl-wrap-narrow bv-wrap">
          <span className="tl-eyebrow">Trust Badge check</span>
          <h1 className="tl-display bv-title">Is this badge<br /><span className="tl-grad-text">real?</span></h1>
          <p className="tl-mono bv-code">Code {code}</p>

          {state.loading && <div className="bv-loading"><span className="tl-spinner" /></div>}

          {state.error && (
            <div className="bv-card tl-card tl-card-pad bv-bad">
              <span className="tl-chip tl-chip-bad">Not found</span>
              <h2>No badge has this code</h2>
              <p>{state.error} If someone showed you a certificate with this code, it wasn’t issued by TrustLens.</p>
            </div>
          )}

          {b && (
            <div className={`bv-card tl-card tl-card-pad bv-${status[1]}`}>
              <span className={`tl-chip tl-chip-${status[1]}`}>{status[0]}</span>
              <h2>@{b.username}</h2>
              <ScoreRing score={b.trust_score} tone={toneFor(b.verdict)} size={200} />
              <dl className="bv-facts">
                <div><dt>Verdict</dt><dd>{b.verdict}</dd></div>
                <div><dt>Issued</dt><dd>{formatDate(b.issued_at)}</dd></div>
                <div><dt>{b.expired ? 'Expired' : 'Valid until'}</dt><dd>{formatDate(b.expires_at)}</dd></div>
              </dl>
              <p className="tl-hint">
                This is the record TrustLens holds. If a certificate you were given shows anything different, trust this page.
                The account’s owner proved it was theirs before the badge was issued. A score is automated evidence from
                public data, not a guarantee.
              </p>
            </div>
          )}
          <Link to="/" className="tl-link">What is TrustLens?</Link>
        </div>
      </section>
    </PageShell>
  )
}

export default BadgeVerify
