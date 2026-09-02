import { useEffect, useState } from 'react'
import { useLocation, Navigate } from 'react-router-dom'
import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Results.css'

function Results() {
  const location = useLocation()
  const result = location.state?.result
  const [revealed, setRevealed] = useState(0)

  if (!result) {
    return <Navigate to="/" replace />
  }

  const colorFromVerdict = (verdict) => {
    if (verdict === 'Trusted') return 'green'
    if (verdict === 'Moderate Risk') return 'yellow'
    return 'red'
  }

  const profile = {
    username: result.username,
    fullName: result.full_name,
    isVerified: result.is_verified,
    trustScore: result.trust_score.trust_score,
    verdict: result.trust_score.verdict,
    color: colorFromVerdict(result.trust_score.verdict),
  }

  const checks = [
    { label: 'Followers analyzed', value: result.raw_profile_data.followers.toLocaleString() },
    { label: 'Fake follower risk', value: `${result.fake_follower_analysis.bot_percentage}%` },
    { label: 'Engagement rate', value: `${result.engagement_analysis.engagement_rate}% — ${result.engagement_analysis.status}` },
    { label: 'Profile completeness', value: profile.isVerified ? 'Verified account' : 'Not verified' },
  ]

  useEffect(() => {
    const timer = setInterval(() => {
      setRevealed((prev) => (prev < checks.length ? prev + 1 : prev))
    }, 350)
    return () => clearInterval(timer)
  }, [])

  const circumference = 2 * Math.PI * 90
  const targetOffset = circumference - (profile.trustScore / 100) * circumference
  const [ringOffset, setRingOffset] = useState(circumference)

  useEffect(() => {
    const timer = setTimeout(() => setRingOffset(targetOffset), 200)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="results-page">
      <Navbar />

      <div className="results-content">
        <div className="results-profile-strip">
          <div className="results-avatar">
            {profile.username.charAt(0).toUpperCase()}
          </div>
          <div>
            <div className="results-fullname">
              {profile.fullName}
              {profile.isVerified && <span className="verified-badge">✓ verified</span>}
            </div>
            <div className="results-username">@{profile.username}</div>
          </div>
        </div>

        <div className="results-main">
          <div className="score-panel">
            <svg className="score-ring" viewBox="0 0 200 200">
              <circle cx="100" cy="100" r="90" className="score-ring-bg" />
              <circle
                cx="100" cy="100" r="90"
                className={`score-ring-fill ring-${profile.color}`}
                style={{
                  strokeDasharray: circumference,
                  strokeDashoffset: ringOffset,
                }}
              />
            </svg>
            <div className="score-ring-center">
              <span className="score-number">{profile.trustScore}</span>
              <span className={`score-verdict verdict-text-${profile.color}`}>
                {profile.verdict}
              </span>
            </div>
          </div>

          <div className="checks-panel">
            <div className="checks-eyebrow">SCAN LOG</div>
            {checks.map((check, i) => (
              <div
                key={check.label}
                className={`check-row ${i < revealed ? 'check-visible' : ''}`}
              >
                <span className="check-mark">{i < revealed ? '✓' : ''}</span>
                <span className="check-label">{check.label}</span>
                <span className="check-value">{i < revealed ? check.value : ''}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="modules-grid">
          <div className="module-card">
            <div className="module-eyebrow">FOLLOWER AUTHENTICITY</div>
            <div className="module-score score-green">{100 - result.fake_follower_analysis.bot_percentage}% Genuine</div>
            <div className="module-desc">{result.fake_follower_analysis.verdict}</div>
          </div>
          <div className="module-card">
            <div className="module-eyebrow">ENGAGEMENT ANALYSIS</div>
            <div className="module-score score-green">{result.engagement_analysis.status}</div>
            <div className="module-desc">{result.engagement_analysis.engagement_rate}% engagement rate — {result.engagement_analysis.tier} tier</div>
          </div>
          <div className="module-card module-pending">
            <div className="module-eyebrow">MISINFORMATION CHECK</div>
            <div className="module-score">—</div>
            <div className="module-desc">Module in development</div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Results