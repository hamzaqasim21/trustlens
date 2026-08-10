import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Dashboard.css'

function Dashboard() {
  const recentScans = [
    { username: 'cristiano', score: 80.5, verdict: 'Trusted', color: 'green' },
    { username: 'suspicious_acc21', score: 22.1, verdict: 'High Risk', color: 'red' },
    { username: 'foodie_lifestyle', score: 61.4, verdict: 'Moderate Risk', color: 'yellow' },
  ]

  return (
    <div className="dashboard-page">
      <Navbar />
      <div className="dashboard-content">
        <div className="dashboard-header">
          <div>
            <div className="dashboard-eyebrow">DASHBOARD</div>
            <h1 className="dashboard-title">Your scans</h1>
          </div>
          <button className="dashboard-new-scan">+ New scan</button>
        </div>

        <div className="dashboard-stats">
          <div className="stat-block">
            <span className="stat-value">3</span>
            <span className="stat-label">Total scans</span>
          </div>
          <div className="stat-block">
            <span className="stat-value">1</span>
            <span className="stat-label">Flagged high risk</span>
          </div>
          <div className="stat-block">
            <span className="stat-value score-yellow">54.6</span>
            <span className="stat-label">Avg trust score</span>
          </div>
        </div>

        <div className="scan-log">
          <div className="scan-log-header">
            <span>Profile</span>
            <span>Trust score</span>
            <span>Verdict</span>
          </div>
          {recentScans.map((scan) => (
            <div className="scan-log-row" key={scan.username}>
              <div className="scan-log-profile">
                <span className={`scan-avatar avatar-${scan.color}`}>
                  {scan.username.charAt(0).toUpperCase()}
                </span>
                <span className="scan-log-username">@{scan.username}</span>
              </div>
              <span className="scan-log-score">{scan.score}</span>
              <span className={`scan-log-verdict verdict-pill-${scan.color}`}>
                <span className="verdict-dot"></span>
                {scan.verdict}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Dashboard