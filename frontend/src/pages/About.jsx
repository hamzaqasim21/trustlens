import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './About.css'

function About() {
  const steps = [
    { tag: 'INGEST', color: 'green', title: 'Real profile data', desc: 'We pull live followers, posts, bio, and engagement directly from the platform — no manual entry.' },
    { tag: 'ANALYZE', color: 'amber', title: 'Trained AI models', desc: 'A Random Forest model — trained on 5,000 labeled profiles — scores follower authenticity in real time.' },
    { tag: 'SCORE', color: 'red', title: 'One trust score', desc: 'Every signal is weighted and combined into a single 0–100 score with a clear verdict.' },
  ]

  return (
    <div className="about-page">
      <Navbar />

      <div className="about-hero">
        <div className="about-hero-shape"></div>
        <div className="about-eyebrow">HOW IT WORKS</div>
        <h1 className="about-title">
          Not a black box.<br />An audit trail.
        </h1>
        <p className="about-subtitle">
          TrustLens doesn't guess — every score is backed by real data and a model
          you can inspect, not a hidden formula.
        </p>
      </div>

      <div className="about-steps">
        {steps.map((step, i) => (
          <div className={`about-step step-${step.color}`} key={step.tag}>
            <div className="about-step-number">{`0${i + 1}`}</div>
            <div>
              <span className={`about-step-tag tag-${step.color}`}>{step.tag}</span>
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="about-stat-banner">
        <div className="about-stat">
          <span className="about-stat-value">99.3%</span>
          <span className="about-stat-label">Model accuracy on test data</span>
        </div>
        <div className="about-stat">
          <span className="about-stat-value">5,000</span>
          <span className="about-stat-label">Labeled profiles trained on</span>
        </div>
        <div className="about-stat">
          <span className="about-stat-value">&lt;3s</span>
          <span className="about-stat-label">Average scan time</span>
        </div>
      </div>
    </div>
  )
}

export default About