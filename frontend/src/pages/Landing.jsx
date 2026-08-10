import { useState } from 'react'
import Navbar from '../components/Navbar'
import '../components/Navbar.css'
import './Landing.css'

function Landing() {
  const [username, setUsername] = useState('')

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
          />
          <button className="scan-box-button">Run scan</button>
        </div>

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