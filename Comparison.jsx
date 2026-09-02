import { useState } from 'react'
import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Comparison.css'
import { analyzeProfile } from '../api/trustlens'

function colorFromVerdict(verdict) {
  if (verdict === 'Trusted') return 'green'
  if (verdict === 'Moderate Risk') return 'yellow'
  return 'red'
}

function ComparisonCard({ result }) {
  const profile = {
    username: result.username,
    score: result.trust_score.trust_score,
    verdict: result.trust_score.verdict,
    color: colorFromVerdict(result.trust_score.verdict),
    followers: result.raw_profile_data.followers.toLocaleString(),
    engagement: `${result.engagement_analysis.engagement_rate}%`,
  }

  return (
    <div className={`comparison-card card-${profile.color}`}>
      <div className="comparison-card-top">
        <div className={`comparison-avatar avatar-${profile.color}`}>
          {profile.username.charAt(0).toUpperCase()}
        </div>
        <div>
          <div className="comparison-username">@{profile.username}</div>
          <div className={`comparison-verdict verdict-text-${profile.color}`}>{profile.verdict}</div>
        </div>
      </div>

      <div className="comparison-score-block">
        <span className="comparison-score-number">{profile.score}</span>
        <span className="comparison-score-label">TRUST SCORE</span>
      </div>

      <div className="comparison-stats">
        <div className="comparison-stat">
          <span className="comparison-stat-label">Followers</span>
          <span className="comparison-stat-value">{profile.followers}</span>
        </div>
        <div className="comparison-stat">
          <span className="comparison-stat-label">Engagement</span>
          <span className="comparison-stat-value">{profile.engagement}</span>
        </div>
      </div>
    </div>
  )
}

function ComparisonCardSkeleton() {
  return (
    <div className="comparison-card comparison-card-skeleton">
      <div className="comparison-card-top">
        <div className="comparison-avatar avatar-skeleton"></div>
        <div>
          <div className="skeleton-line skeleton-line-short"></div>
          <div className="skeleton-line skeleton-line-shorter"></div>
        </div>
      </div>
      <div className="comparison-score-block">
        <div className="skeleton-line skeleton-line-score"></div>
      </div>
    </div>
  )
}

function Comparison() {
  const [usernameA, setUsernameA] = useState('')
  const [usernameB, setUsernameB] = useState('')
  const [resultA, setResultA] = useState(null)
  const [resultB, setResultB] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleCompare() {
    if (!usernameA.trim() || !usernameB.trim()) return

    setLoading(true)
    setError('')
    setResultA(null)
    setResultB(null)

    try {
      const [a, b] = await Promise.all([
        analyzeProfile(usernameA.trim()),
        analyzeProfile(usernameB.trim()),
      ])
      setResultA(a)
      setResultB(b)
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
    }
  }

  const hasResults = resultA && resultB

  return (
    <div className="comparison-page">
      <Navbar />

      <div className="comparison-hero">
        <div className="comparison-hero-shape"></div>
        <div className="comparison-eyebrow">SIDE-BY-SIDE VERIFICATION</div>
        <h1 className="comparison-title">Compare two profiles head-to-head</h1>

        <div className="comparison-input-row">
          <input
            type="text"
            placeholder="first_username"
            value={usernameA}
            onChange={(e) => setUsernameA(e.target.value)}
            className="comparison-input"
            disabled={loading}
          />
          <span className="comparison-input-vs">vs</span>
          <input
            type="text"
            placeholder="second_username"
            value={usernameB}
            onChange={(e) => setUsernameB(e.target.value)}
            className="comparison-input"
            disabled={loading}
          />
          <button className="comparison-compare-button" onClick={handleCompare} disabled={loading}>
            {loading ? 'Comparing...' : 'Compare'}
          </button>
        </div>

        {error && <p className="comparison-error">{error}</p>}
      </div>

      <div className="comparison-content">
        <div className="comparison-grid">
          {loading && (
            <>
              <ComparisonCardSkeleton />
              <ComparisonCardSkeleton />
            </>
          )}
          {!loading && hasResults && (
            <>
              <ComparisonCard result={resultA} />
              <ComparisonCard result={resultB} />
            </>
          )}
          {!loading && !hasResults && (
            <div className="comparison-empty-state">
              Enter two usernames above to see how they stack up.
            </div>
          )}
        </div>

        {!loading && hasResults && <div className="comparison-vs">VS</div>}
      </div>
    </div>
  )
}

export default Comparison
