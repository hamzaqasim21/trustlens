import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import Brand from './Brand'

function SiteFooter() {
  const { user } = useAuth()
  return (
    <footer className="tl-foot">
      <div className="tl-wrap">
        <div className="tl-foot-grid">
          <div>
            <Brand />
            <p className="tl-foot-tagline">
              Know who's real before you trust them. A multi-modal framework for social media authenticity and fraud detection.
            </p>
          </div>
          <div className="tl-foot-col">
            <b>PRODUCT</b>
            <Link to="/scan">Scan a profile</Link>
            <Link to="/comparison">Compare accounts</Link>
            <Link to="/extension">Chrome extension</Link>
            {user ? <Link to="/dashboard">Your dashboard</Link> : <Link to="/signup">Create an account</Link>}
          </div>
          <div className="tl-foot-col">
            <b>LEARN</b>
            <Link to="/about">How it works</Link>
            <Link to="/methodology">Methodology</Link>
            <Link to="/#pricing">Pricing</Link>
            <Link to="/#faq">FAQ</Link>
          </div>
          <div className="tl-foot-col">
            <b>PROJECT</b>
            <span>Final Year Project</span>
            <span>Air University Islamabad</span>
            <span>Faculty of Computing and AI</span>
          </div>
        </div>
        <div className="tl-foot-bottom">
          <span>© 2026 TrustLens · Final Year Project</span>
          <span>Scores are an aid to judgement, not a verdict on a person.</span>
        </div>
      </div>
      <div className="tl-foot-wordmark tl-display" aria-hidden="true">TrustLens</div>
    </footer>
  )
}

export default SiteFooter
