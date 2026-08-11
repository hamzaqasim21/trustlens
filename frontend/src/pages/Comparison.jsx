import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Comparison.css'

function Comparison() {
  const profiles = [
    { username: 'cristiano', score: 80.5, verdict: 'Trusted', color: 'green', followers: '678.2M', engagement: '2.15%' },
    { username: 'suspicious_acc21', score: 22.1, verdict: 'High Risk', color: 'red', followers: '412K', engagement: '0.08%' },
  ]

  return (
    <div className="comparison-page">
      <Navbar />

      <div className="comparison-hero">
        <div className="comparison-hero-shape"></div>
        <div className="comparison-eyebrow">SIDE-BY-SIDE VERIFICATION</div>
        <h1 className="comparison-title">Compare two profiles head-to-head</h1>
      </div>

      <div className="comparison-content">
        <div className="comparison-grid">
          {profiles.map((p) => (
            <div className={`comparison-card card-${p.color}`} key={p.username}>
              <div className="comparison-card-top">
                <div className={`comparison-avatar avatar-${p.color}`}>
                  {p.username.charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="comparison-username">@{p.username}</div>
                  <div className={`comparison-verdict verdict-text-${p.color}`}>{p.verdict}</div>
                </div>
              </div>

              <div className="comparison-score-block">
                <span className="comparison-score-number">{p.score}</span>
                <span className="comparison-score-label">TRUST SCORE</span>
              </div>

              <div className="comparison-stats">
                <div className="comparison-stat">
                  <span className="comparison-stat-label">Followers</span>
                  <span className="comparison-stat-value">{p.followers}</span>
                </div>
                <div className="comparison-stat">
                  <span className="comparison-stat-label">Engagement</span>
                  <span className="comparison-stat-value">{p.engagement}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="comparison-vs">VS</div>
      </div>
    </div>
  )
}

export default Comparison