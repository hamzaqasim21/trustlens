import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Landing.css'
import { analyzeProfile } from '../api/trustlens'

function Landing() {
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function handleScan() {
    if (!username.trim()) return

    setLoading(true)
    setError('')

    try {
      const result = await analyzeProfile(username.trim())
      navigate('/results', { state: { result } })
    } catch (err) {
      setError(err.message || 'Something went wrong. Try again.')
      setLoading(false)
    }
  }

  return (
    <div className="landing">
      <Navbar />

      <section className="hero">
        <div className="hero-eyebrow">PROFILE AUTHENTICITY CHECK</div>
        <h1 className="hero-title">
          Before you trust an account,<br />verify it.
        </h1>
        <p className="hero-subtitle">
          TrustLens scans any public Instagram profile for fake followers,
          suspicious engagement, and manipulated credentials — in seconds.
        </p>

        <div className="scan-box">
          <span className="scan-box-at">@</span>
          <input
            type="text"
            placeholder="instagram_username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="scan-box-input"
            disabled={loading}
          />
          <button className="scan-box-button" onClick={handleScan} disabled={loading}>
            {loading ? 'Scanning...' : 'Run scan'}
          </button>
        </div>

        {error && <p className="scan-error">{error}</p>}

        <div className="hero-checks">
          <span>✓ Fake follower detection</span>
          <span>✓ Engagement authenticity</span>
          <span>✓ Deepfake screening</span>
        </div>
      </section>
    </div>
  )
}

export default Landing