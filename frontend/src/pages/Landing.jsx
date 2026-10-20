import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './Landing.css'
import { useAuth } from '../context/AuthContext'
import CountUp from '../components/CountUp'
import SiteNav from '../components/site/SiteNav'
import SiteFooter from '../components/site/SiteFooter'
import Reveal from '../components/site/Reveal'
import { parseUsername, savePendingScan, scanPath, USERNAME_HELP } from '../lib/scanFlow'

// Real verdict thresholds, unchanged from the previous design — these are
// the actual ones from backend/trust_score.py (>=70 Trusted, >=40 Moderate
// Risk, else High Risk). If those ever change, change them here too.
const SCORE_BANDS = [
  { from: 0, to: 40, color: '#FF6B5B' },
  { from: 40, to: 70, color: '#F2B84D' },
  { from: 70, to: 100, color: '#00D4AA' },
]

// The sticker over the phone illustration is a KEY to the score, not a
// result — it teaches the three verdict bands before anyone has scanned
// anything, the same honest reasoning as the ring this replaced (see the
// git history on this file for the "94 — TRUSTED" story if it ever comes
// up again). The math is the same real math; only the container changed.
function TrustScoreSticker() {
  const [drawn, setDrawn] = useState(false)
  const radius = 70
  const circumference = 2 * Math.PI * radius

  useEffect(() => {
    const timer = setTimeout(() => setDrawn(true), 300)
    return () => clearTimeout(timer)
  }, [])

  return (
    <svg viewBox="0 0 200 200" role="img" aria-label="The Trust Score scale: 0 to 100">
      <circle cx="100" cy="100" r="96" fill="#2B1140" stroke="#00D4AA" strokeWidth="4" />
      <g transform="rotate(-90 100 100)" fill="none" strokeWidth="13">
        <circle cx="100" cy="100" r={radius} stroke="rgba(255,255,255,0.12)" />
        {SCORE_BANDS.map((band) => {
          const length = ((band.to - band.from) / 100) * circumference
          // A 2px visual gap between bands so they read as three distinct
          // zones rather than one continuous ring.
          const shown = drawn ? Math.max(length - 3, 0) : 0
          return (
            <circle
              key={band.from}
              className="ig-ring-band"
              cx="100" cy="100" r={radius}
              stroke={band.color}
              strokeDasharray={`${shown} ${circumference - shown}`}
              strokeDashoffset={-(band.from / 100) * circumference}
            />
          )
        })}
      </g>
      <text x="100" y="104" textAnchor="middle" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="32" fontWeight="800" letterSpacing="-1.5">0–100</text>
      <text x="100" y="124" textAnchor="middle" fill="#00D4AA" fontFamily="JetBrains Mono, monospace" fontSize="9.5" fontWeight="700" letterSpacing="1.6">TRUST SCORE</text>
    </svg>
  )
}

function Landing() {
  const [username, setUsername] = useState('')
  const [message, setMessage] = useState('')
  const navigate = useNavigate()
  const { user, loading: authLoading } = useAuth()

  useEffect(() => { document.title = 'TrustLens · Real or not?' }, [])

  // The pipeline: a logged-out visitor is sent to sign up first, with the
  // username remembered, and the scan runs by itself the moment the account
  // is ready. A logged-in visitor goes straight to the scan. Either way the
  // scan itself happens on /scan, which shows progress while it runs.
  // (The backend also refuses scans without a login, so this can't be
  // skipped by calling the API directly.)
  function handleScan(e) {
    e.preventDefault()
    const name = parseUsername(username)
    if (!name) {
      setMessage(username.trim() ? USERNAME_HELP : 'Type a username first, for example @lahore.eats')
      return
    }
    if (authLoading) return
    if (!user) {
      savePendingScan(name)
      navigate('/signup')
      return
    }
    navigate(scanPath(name))
  }

  return (
    <div className="tl-page landing-ig">
      <SiteNav />
      {/* Shared collage patterns, referenced by the illustrations below. */}
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
        <defs>
          <pattern id="zig-green" width="36" height="22" patternUnits="userSpaceOnUse">
            <path d="M-2 16 L7 5 L16 16 L25 5 L34 16 L43 5" fill="none" stroke="#00D4AA" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round"/>
          </pattern>
          <pattern id="zig-indigo" width="36" height="22" patternUnits="userSpaceOnUse" patternTransform="translate(9 11)">
            <path d="M-2 16 L7 5 L16 16 L25 5 L34 16 L43 5" fill="none" stroke="#833AB4" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round"/>
          </pattern>
          <pattern id="wave-aqua" width="48" height="18" patternUnits="userSpaceOnUse">
            <path d="M0 9 Q12 1 24 9 T48 9" fill="none" stroke="#405DE6" strokeWidth="4" strokeLinecap="round"/>
          </pattern>
          <pattern id="seeds" width="34" height="30" patternUnits="userSpaceOnUse">
            <ellipse cx="9" cy="8" rx="2.6" ry="4.4" fill="#2B1B3F" transform="rotate(20 9 8)"/>
            <ellipse cx="26" cy="23" rx="2.6" ry="4.4" fill="#2B1B3F" transform="rotate(-15 26 23)"/>
          </pattern>
          <pattern id="diamond" width="44" height="44" patternUnits="userSpaceOnUse">
            <rect width="44" height="44" fill="#FCAF45"/>
            <path d="M22 0 L44 22 L22 44 L0 22 Z" fill="#405DE6"/>
            <path d="M22 11 L33 22 L22 33 L11 22 Z" fill="#833AB4"/>
          </pattern>
          <pattern id="dots-indigo" width="16" height="16" patternUnits="userSpaceOnUse">
            <circle cx="4" cy="4" r="2" fill="#833AB4" opacity="0.35"/>
          </pattern>
          <pattern id="squig-pink" width="40" height="30" patternUnits="userSpaceOnUse">
            <path d="M0 15 C 8 2, 12 28, 20 15 S 32 2, 40 15" stroke="#FFC6DD" strokeWidth="4" fill="none" strokeLinecap="round"/>
          </pattern>
        </defs>
      </svg>

      {/* ================================================================ HERO */}
      <header className="ig-hero">
        <div className="ig-wrap">
          <div className="ig-hero-grid" id="top">
            <h1 className="ig-hero-title ig-display">REAL<br/>OR NOT?</h1>

            <div className="ig-hero-intro">
              <p>Welcome to <strong>TrustLens</strong>, the free check that tells you whether an Instagram creator is real before you trust their advice, buy their product or pay for their post.</p>
              <a className="ig-pill ig-pill-gradient ig-pill-hero" href="#scan">Start a scan</a>
            </div>

            {/* Real, held-out-test numbers (see Landing.jsx's earlier design
                notes) — brought back at Hamza's request to fill the wide
                flanking gaps either side of the phone at a full desktop
                width, not as a "speed sells it" pitch. */}
            <div className="ig-hero-stats">
              <div className="ig-hero-stat">
                <span className="ig-hero-stat-value"><CountUp value={95.8} decimals={1} duration={1200} />%</span>
                <span className="ig-hero-stat-label">Fake-account model accuracy</span>
              </div>
              <div className="ig-hero-stat">
                <span className="ig-hero-stat-value"><CountUp value={77} duration={1200} />%</span>
                <span className="ig-hero-stat-label">Misinformation classifier accuracy</span>
              </div>
              <div className="ig-hero-stat">
                <span className="ig-hero-stat-value">&lt;60s</span>
                <span className="ig-hero-stat-label">For a full four-check scan</span>
              </div>
            </div>

            <div className="ig-phone-wrap">
              <svg className="ig-phone" viewBox="0 0 300 540" role="img" aria-label="Illustration: a sponsored Instagram post with a TrustLens badge reading Looks OK">
                <defs><clipPath id="phone-clip"><rect width="300" height="540" rx="28"/></clipPath></defs>
                <g clipPath="url(#phone-clip)">
                  <rect width="300" height="540" fill="#FF9EC4"/>
                  <path d="M-10 70 C 60 30, 110 120, 180 80 S 290 40, 320 100 L320 180 C 250 140, 200 220, 130 180 S 20 130, -10 180 Z" fill="#FF6FAE"/>
                  <path d="M-10 250 C 50 210, 90 300, 170 260 S 280 220, 320 280 L320 330 C 260 300, 220 360, 150 320 S 30 290, -10 330 Z" fill="#FFC6DD"/>
                  <path d="M-10 390 C 70 360, 110 440, 190 410 S 290 370, 320 430 L320 540 L-10 540 Z" fill="#FF6FAE"/>
                  <text x="92" y="38" fill="#FFFFFF" opacity="0.75" fontFamily="Archivo, Arial, sans-serif" fontSize="13" fontWeight="600">Following</text>
                  <text x="172" y="38" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="13" fontWeight="800">For you</text>
                  <rect x="180" y="45" width="34" height="3" rx="1.5" fill="#FFFFFF"/>
                  <g transform="translate(16 62)">
                    <rect width="164" height="30" rx="15" fill="#833AB4"/>
                    <circle cx="17" cy="15" r="6" fill="#00D4AA"/>
                    <text x="30" y="19.5" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="12" fontWeight="700">TrustLens · Looks OK</text>
                  </g>
                  <circle cx="92" cy="256" r="82" fill="#FCAF45"/>
                  <path d="M28 540 C 32 432, 80 394, 150 390 C 220 394, 268 432, 272 540 Z" fill="#405DE6"/>
                  <g stroke="#2DB3AA" strokeWidth="3" opacity="0.8">
                    <path d="M70 450 L66 540"/><path d="M96 432 L94 540"/><path d="M204 432 L206 540"/><path d="M230 450 L234 540"/>
                  </g>
                  <path d="M128 330 L128 398 C 140 412, 160 412, 172 398 L172 330 Z" fill="#5A3020"/>
                  <path d="M110 394 C 124 414, 176 414, 190 394" stroke="#405DE6" strokeWidth="11" fill="none" strokeLinecap="round"/>
                  <ellipse cx="86" cy="278" rx="10" ry="16" fill="#62331F"/>
                  <ellipse cx="214" cy="278" rx="10" ry="16" fill="#62331F"/>
                  <ellipse cx="150" cy="270" rx="64" ry="79" fill="#6E3B27"/>
                  <path d="M86 252 C 84 198, 116 177, 150 177 C 186 177, 216 198, 214 252 C 206 224, 186 211, 150 211 C 116 211, 94 224, 86 252 Z" fill="#1B1020"/>
                  <g stroke="#FCAF45" strokeWidth="9" strokeLinecap="round">
                    <circle cx="122" cy="267" r="24" fill="#2A160E"/>
                    <circle cx="178" cy="267" r="24" fill="#2A160E"/>
                    <path d="M146 264 L154 264"/><path d="M98 263 L87 259"/><path d="M202 263 L213 259"/>
                  </g>
                  <path d="M110 257 A 14 14 0 0 1 124 251" stroke="#FFFFFF" strokeWidth="3" fill="none" opacity="0.55" strokeLinecap="round"/>
                  <path d="M166 257 A 14 14 0 0 1 180 251" stroke="#FFFFFF" strokeWidth="3" fill="none" opacity="0.55" strokeLinecap="round"/>
                  <path d="M150 286 C 146 300, 144 306, 152 309" stroke="#4E2717" strokeWidth="3" fill="none" strokeLinecap="round"/>
                  <path d="M131 324 C 142 333, 160 333, 171 322" stroke="#3B1A10" strokeWidth="4" fill="none" strokeLinecap="round"/>
                  <g fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="10" fontWeight="700" textAnchor="middle">
                    <circle cx="266" cy="336" r="17" fill="#FFFFFF" opacity="0.28"/>
                    <path d="M266 343 L257 334 C 253 330, 256 323, 261.5 324.5 C 263.5 325, 265 326.5, 266 328 C 267 326.5, 268.5 325, 270.5 324.5 C 276 323, 279 330, 275 334 Z"/>
                    <text x="266" y="367">48.2K</text>
                    <circle cx="266" cy="392" r="17" fill="#FFFFFF" opacity="0.28"/>
                    <path d="M257 386 h18 a3 3 0 0 1 3 3 v9 a3 3 0 0 1 -3 3 h-10 l-6 5 v-5 h-2 a3 3 0 0 1 -3 -3 v-9 a3 3 0 0 1 3 -3 Z"/>
                    <text x="266" y="423">1,204</text>
                    <circle cx="266" cy="448" r="17" fill="#FFFFFF" opacity="0.28"/>
                    <path d="M259 454 L259 449 C 259 444, 263 441, 269 441 L269 436 L277 444 L269 452 L269 447 C 265 447, 261 449, 259 454 Z"/>
                  </g>
                  <rect x="0" y="474" width="300" height="66" fill="#2B1140" opacity="0.86"/>
                  <text x="18" y="499" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="14" fontWeight="800">@lahore.eats</text>
                  <text x="18" y="519" fill="#FFFFFF" opacity="0.85" fontFamily="Archivo, Arial, sans-serif" fontSize="11.5">Use code EID20 for 20% off. Link in bio.</text>
                </g>
              </svg>

              <div className="ig-sticker">
                <TrustScoreSticker />
                <div className="ig-band-key" aria-label="Score bands">
                  <span><i className="ig-key-dot" style={{ background: '#00D4AA' }} />70+ Trusted</span>
                  <span><i className="ig-key-dot" style={{ background: '#F2B84D' }} />40–69 Moderate</span>
                  <span><i className="ig-key-dot" style={{ background: '#FF6B5B' }} />&lt;40 High risk</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ============================================================ MARQUEE */}
      <div className="ig-band" aria-label="What TrustLens checks">
        <div className="ig-marquee">
          <span>Fake accounts <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>Bought engagement <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>Scam captions <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>Fake credentials <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>English + Urdu <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>Chrome extension <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span>Score reports <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Fake accounts <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Bought engagement <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Scam captions <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Fake credentials <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">English + Urdu <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Chrome extension <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
          <span aria-hidden="true">Score reports <svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="7" fill="none" stroke="#FFFFFF" strokeWidth="3.5"/></svg></span>
        </div>
      </div>

      <main>
        {/* ============================================================ ABOUT */}
        <section className="ig-block ig-on-lime ig-about" id="about">
          <div className="ig-wrap ig-about-grid">
            <div style={{ display: 'grid', gap: 'clamp(36px, 5vw, 64px)' }}>
              <h2 className="ig-about-title ig-display">About<br/>TrustLens</h2>
              <svg className="ig-collage" viewBox="0 0 400 400" role="img" aria-label="Illustration: a magnifying lens over a grid of follower avatars, three of them flagged">
                <rect width="400" height="400" fill="#405DE6"/>
                <rect width="400" height="400" fill="url(#wave-aqua)"/>
                <g>
                  <circle cx="70" cy="70" r="17" fill="#FFFFFF"/><circle cx="135" cy="70" r="17" fill="#833AB4"/><circle cx="200" cy="70" r="17" fill="#00D4AA"/><circle cx="265" cy="70" r="17" fill="#E1306C"/><circle cx="330" cy="70" r="17" fill="#FFFFFF"/>
                  <circle cx="70" cy="135" r="17" fill="#E1306C"/><circle cx="135" cy="135" r="17" fill="#FFFFFF"/><circle cx="200" cy="135" r="17" fill="#833AB4"/><circle cx="265" cy="135" r="17" fill="#FFFFFF"/><circle cx="330" cy="135" r="17" fill="#00D4AA"/>
                  <circle cx="70" cy="200" r="17" fill="#00D4AA"/><circle cx="135" cy="200" r="17" fill="#833AB4"/><circle cx="200" cy="200" r="17" fill="#F77737"/><circle cx="265" cy="200" r="17" fill="#F77737"/><circle cx="330" cy="200" r="17" fill="#833AB4"/>
                  <circle cx="70" cy="265" r="17" fill="#FFFFFF"/><circle cx="135" cy="265" r="17" fill="#E1306C"/><circle cx="200" cy="265" r="17" fill="#FFFFFF"/><circle cx="265" cy="265" r="17" fill="#F77737"/><circle cx="330" cy="265" r="17" fill="#E1306C"/>
                  <circle cx="70" cy="330" r="17" fill="#833AB4"/><circle cx="135" cy="330" r="17" fill="#00D4AA"/><circle cx="200" cy="330" r="17" fill="#FFFFFF"/><circle cx="265" cy="330" r="17" fill="#833AB4"/><circle cx="330" cy="330" r="17" fill="#FFFFFF"/>
                </g>
                <g stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round">
                  <path d="M193 193 L207 207 M207 193 L193 207"/><path d="M258 193 L272 207 M272 193 L258 207"/><path d="M258 258 L272 272 M272 258 L258 272"/>
                </g>
                <circle cx="232" cy="222" r="92" fill="rgba(255,255,255,0.22)" stroke="#00D4AA" strokeWidth="16"/>
                <circle cx="232" cy="222" r="74" fill="none" stroke="#2B1140" strokeWidth="3" opacity="0.6"/>
                <rect x="290" y="262" width="30" height="118" rx="15" fill="#2B1140" transform="rotate(-45 305 321)"/>
              </svg>
            </div>

            <Reveal className="ig-about-side">
              <div className="ig-row">
                <span className="ig-ask">Who?</span>
                <a className="ig-pill ig-pill-outline-dark" href="#how">Learn more</a>
              </div>
              <div className="ig-about-copy">
                <p>We're not another follower counter. TrustLens is a final-year project from Air University Islamabad, built because Pakistan saw more than 13,000 online fraud complaints in 2024, many of them starting with a creator nobody had checked.</p>
                <p>Fake doctors selling cures. "Advisors" promising guaranteed returns. Brands paying for followers who don't exist. Each scan runs four independent checks and shows the reasoning behind every number, so you can see <em>why</em> an account earns its score, not just the score.</p>
                <p>And if a score looks wrong, you can report it. A person reviews every report within 48 hours.</p>
              </div>
            </Reveal>
          </div>
        </section>

        {/* =========================================================== CHECKS */}
        <section className="ig-block ig-on-lime" id="checks" style={{ paddingTop: 0 }}>
          <div className="ig-wrap">
            <div className="ig-checks-head">
              <div className="ig-checks-intro">
                <span className="ig-ask">What?</span>
                <p>Four checks run on every scan. Each scores the account on its own, then the Trust Score weighs them together, and says plainly when one couldn't run, instead of guessing.</p>
              </div>
              <h2 className="ig-checks-title ig-display">Trust<br/>Checks</h2>
            </div>

            <div className="ig-checks-grid">
              <Reveal as="article" delay={0} className="ig-check">
                <figure>
                  <svg viewBox="0 0 300 300" role="img" aria-label="Illustration: a profile with no photo, no posts and 4,200 following, stamped bot-like">
                    <rect width="300" height="300" fill="#E1306C"/>
                    <rect width="300" height="300" fill="url(#zig-indigo)"/>
                    <rect width="300" height="300" fill="url(#zig-green)"/>
                    <rect x="44" y="64" width="212" height="168" rx="18" fill="#FFFFFF"/>
                    <circle cx="86" cy="110" r="24" fill="#EDEAFB" stroke="#B8B1EE" strokeWidth="3" strokeDasharray="5 5"/>
                    <text x="120" y="106" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="13" fontWeight="800">@user_88374621</text>
                    <text x="120" y="124" fill="#7A74A8" fontFamily="Archivo, Arial, sans-serif" fontSize="11">No bio</text>
                    <g fontFamily="Archivo, Arial, sans-serif" textAnchor="middle">
                      <text x="86" y="172" fill="#2B1140" fontSize="19" fontWeight="800">0</text>
                      <text x="150" y="172" fill="#2B1140" fontSize="19" fontWeight="800">4,200</text>
                      <text x="216" y="172" fill="#2B1140" fontSize="19" fontWeight="800">12</text>
                      <text x="86" y="190" fill="#7A74A8" fontSize="10.5">posts</text>
                      <text x="150" y="190" fill="#7A74A8" fontSize="10.5">following</text>
                      <text x="216" y="190" fill="#7A74A8" fontSize="10.5">followers</text>
                    </g>
                    <g transform="rotate(-11 190 232)">
                      <rect x="118" y="212" width="144" height="42" rx="6" fill="#FFFFFF" stroke="#E0412F" strokeWidth="4"/>
                      <text x="190" y="241" textAnchor="middle" fill="#E0412F" fontFamily="Archivo, Arial, sans-serif" fontSize="21" fontWeight="900" letterSpacing="2">BOT-LIKE</text>
                    </g>
                  </svg>
                </figure>
                <div className="ig-check-top"><h3>Fake accounts</h3><span className="ig-tag ig-tag-ai">AI MODEL</span></div>
                <p>A trained Random Forest judges whether the account itself looks fake from its own profile: followers, following, posts, photo, bio and username.</p>
              </Reveal>

              <Reveal as="article" delay={80} className="ig-check">
                <figure>
                  <svg viewBox="0 0 300 300" role="img" aria-label="Illustration: a post with an engagement rate of 0.35 percent circled">
                    <rect width="300" height="300" fill="#833AB4"/>
                    <path d="M14 152 C 80 108, 200 190, 288 128 L292 178 C 210 234, 90 152, 18 204 Z" fill="#FCAF45"/>
                    <rect x="58" y="62" width="184" height="178" rx="18" fill="#FFFFFF"/>
                    <rect x="72" y="76" width="156" height="72" rx="12" fill="#405DE6"/>
                    <rect x="72" y="76" width="156" height="72" rx="12" fill="url(#wave-aqua)"/>
                    <path d="M84 178 L77 171 C 74 168, 76 162, 80.5 163.2 C 82 163.6, 83.2 164.8, 84 166 C 84.8 164.8, 86 163.6, 87.5 163.2 C 92 162, 94 168, 91 171 Z" fill="#E1306C"/>
                    <text x="100" y="176" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="12" fontWeight="700">1.9K likes · 500K followers</text>
                    <text x="150" y="216" textAnchor="middle" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="32" fontWeight="900" letterSpacing="-1">0.35%</text>
                    <ellipse cx="150" cy="206" rx="70" ry="25" fill="none" stroke="#E1306C" strokeWidth="4" transform="rotate(-4 150 206)"/>
                    <text x="150" y="274" textAnchor="middle" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="13" fontWeight="700">Normal for this size: about 1.5%</text>
                  </svg>
                </figure>
                <div className="ig-check-top"><h3>Engagement</h3><span className="ig-tag ig-tag-rules">RULES</span></div>
                <p>Likes and comments measured against what's normal for an account that size. Bought followers rarely engage, so the gap shows.</p>
              </Reveal>

              <Reveal as="article" delay={160} className="ig-check">
                <figure>
                  <svg viewBox="0 0 300 300" role="img" aria-label="Illustration: a scam caption crossed out, and an ordinary ad marked as just an ad">
                    <rect width="300" height="300" fill="#F77737"/>
                    <rect width="300" height="300" fill="url(#seeds)"/>
                    <g transform="rotate(-3 150 102)">
                      <rect x="24" y="66" width="252" height="72" rx="4" fill="#FFF8E7"/>
                      <rect x="36" y="80" width="196" height="24" fill="#FCAF45"/>
                      <text x="40" y="99" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="20" fontWeight="900">GUARANTEED 300%</text>
                      <text x="40" y="124" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="15" fontWeight="800">RETURNS IN 7 DAYS</text>
                      <path d="M34 106 L70 94 L104 108 L140 92 L176 108 L212 94 L244 106" fill="none" stroke="#D92E1C" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </g>
                    <g transform="rotate(2 150 206)">
                      <rect x="24" y="172" width="252" height="68" rx="4" fill="#FFF8E7"/>
                      <text x="40" y="202" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="17" fontWeight="800">New video out now.</text>
                      <text x="40" y="224" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="14">Link in bio</text>
                      <circle cx="246" cy="206" r="17" fill="#00D4AA"/>
                      <path d="M238 206 L244 212 L255 199" fill="none" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
                    </g>
                    <text x="150" y="276" textAnchor="middle" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="13" fontWeight="800">Scam pattern flagged. Ordinary ad left alone.</text>
                  </svg>
                </figure>
                <div className="ig-check-top"><h3>Misinformation</h3><span className="ig-tag ig-tag-mix">AI + RULES</span></div>
                <p>A fine-tuned language model reads the bio and recent captions in English and Urdu, cross-checked against concrete scam wording so ordinary ads aren't called scams.</p>
              </Reveal>

              <Reveal as="article" delay={240} className="ig-check">
                <figure>
                  <svg viewBox="0 0 300 300" role="img" aria-label="Illustration: a bio claiming to be a doctor, stamped claim found, not verified">
                    <rect width="300" height="300" fill="url(#diamond)"/>
                    <rect x="38" y="74" width="224" height="146" rx="18" fill="#FFFFFF"/>
                    <circle cx="78" cy="116" r="20" fill="#E1306C"/>
                    <rect x="104" y="112" width="136" height="9" rx="3" fill="#00D4AA"/>
                    <text x="106" y="114" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="15" fontWeight="800">Dr. Sara Khan, MD</text>
                    <text x="106" y="134" fill="#7A74A8" fontFamily="Archivo, Arial, sans-serif" fontSize="11">Cardiologist · Lahore</text>
                    <text x="58" y="172" fill="#2B1140" fontFamily="Archivo, Arial, sans-serif" fontSize="12">Book a consult. Link in bio.</text>
                    <g transform="rotate(7 170 222)">
                      <rect x="84" y="198" width="172" height="46" rx="8" fill="#2B1140"/>
                      <text x="170" y="217" textAnchor="middle" fill="#00D4AA" fontFamily="JetBrains Mono, monospace" fontSize="12.5" fontWeight="700" letterSpacing="1.2">CLAIM FOUND</text>
                      <text x="170" y="234" textAnchor="middle" fill="#FFFFFF" fontFamily="JetBrains Mono, monospace" fontSize="11" fontWeight="500" letterSpacing="1">NOT VERIFIED</text>
                    </g>
                  </svg>
                </figure>
                <div className="ig-check-top"><h3>Credentials</h3><span className="ig-tag ig-tag-rules">RULES</span></div>
                <p>Finds claims like "Dr.", "MBBS" or "CFA" in the bio. A doctor claim is looked up in the PMDC and US NPI public registers; claims with no public register are shown but not scored.</p>
              </Reveal>
            </div>
          </div>
        </section>

        {/* ========================================================== PROCESS */}
        <section className="ig-block ig-on-indigo ig-process" id="how">
          <div className="ig-wrap">
            <div className="ig-process-head">
              <h2 className="ig-process-title ig-display">Process</h2>
              <div className="ig-process-side">
                <span className="ig-ask">How?</span>
                <p>Type a username, get a score you can actually explain. Nothing is estimated for display. Every number comes from a check that really ran.</p>
                <a className="ig-pill ig-pill-outline-dark" href="#faq">Read the details</a>
              </div>
            </div>

            <ol className="ig-steps">
              <Reveal as="li" delay={0} className="ig-step">
                <figure>
                  <svg viewBox="0 0 300 200" role="img" aria-label="Illustration: a search box containing an Instagram username">
                    <rect width="300" height="200" fill="#E1306C"/>
                    <rect width="300" height="200" fill="url(#squig-pink)"/>
                    <rect x="28" y="76" width="244" height="50" rx="25" fill="#FFFFFF"/>
                    <text x="54" y="107" fill="#2B1140" fontFamily="JetBrains Mono, monospace" fontSize="16" fontWeight="700">@creator.name</text>
                    <rect x="190" y="90" width="2.5" height="22" fill="#2B1140"/>
                    <circle cx="243" cy="99" r="8.5" fill="none" stroke="#2B1140" strokeWidth="3"/>
                    <path d="M249.5 105.5 L255 111" stroke="#2B1140" strokeWidth="3.5" strokeLinecap="round"/>
                  </svg>
                </figure>
                <span className="ig-step-num">STEP 1</span>
                <h3>Type a username</h3>
                <p>Any public Instagram account. Nothing to install and no login needed to try it.</p>
              </Reveal>
              <Reveal as="li" delay={90} className="ig-step">
                <figure>
                  <svg viewBox="0 0 300 200" role="img" aria-label="Illustration: profile, recent posts and captions arriving as cards">
                    <rect width="300" height="200" fill="#405DE6"/>
                    <rect width="300" height="200" fill="url(#wave-aqua)"/>
                    <g fontFamily="Archivo, Arial, sans-serif" fontWeight="800" fontSize="14" fill="#2B1140">
                      <g transform="rotate(-6 150 60)"><rect x="60" y="36" width="180" height="42" rx="12" fill="#FFFFFF"/><text x="82" y="62">Profile</text><circle cx="214" cy="57" r="7" fill="#E1306C"/></g>
                      <g transform="rotate(3 150 104)"><rect x="60" y="82" width="180" height="42" rx="12" fill="#00D4AA"/><text x="82" y="108">Recent posts</text><circle cx="214" cy="103" r="7" fill="#833AB4"/></g>
                      <g transform="rotate(-2 150 148)"><rect x="60" y="128" width="180" height="42" rx="12" fill="#FFFFFF"/><text x="82" y="154">Captions</text><circle cx="214" cy="149" r="7" fill="#FCAF45"/></g>
                    </g>
                  </svg>
                </figure>
                <span className="ig-step-num">STEP 2</span>
                <h3>Real data comes in</h3>
                <p>The public profile, recent posts and captions are fetched live, nothing typed in by hand.</p>
              </Reveal>
              <Reveal as="li" delay={180} className="ig-step">
                <figure>
                  <svg viewBox="0 0 300 200" role="img" aria-label="Illustration: four checks side by side">
                    <rect width="300" height="200" fill="#00D4AA"/>
                    <rect width="300" height="200" fill="url(#dots-indigo)"/>
                    <g fontFamily="JetBrains Mono, monospace" fontSize="10.5" fontWeight="700" fill="#2B1140" textAnchor="middle">
                      <circle cx="57" cy="92" r="30" fill="#833AB4"/><text x="57" y="146">ACCOUNT</text>
                      <circle cx="119" cy="92" r="30" fill="#E1306C"/><text x="119" y="146">ENGAGE</text>
                      <circle cx="181" cy="92" r="30" fill="#405DE6"/><text x="181" y="146">MISINFO</text>
                      <circle cx="243" cy="92" r="30" fill="#F77737"/><text x="243" y="146">CLAIMS</text>
                    </g>
                    <g fill="none" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M46 92 L54 100 L68 84"/><path d="M108 92 L116 100 L130 84"/><path d="M170 92 L178 100 L192 84"/><path d="M232 92 L240 100 L254 84"/>
                    </g>
                  </svg>
                </figure>
                <span className="ig-step-num">STEP 3</span>
                <h3>Four checks run</h3>
                <p>Each check scores the account independently, and says so when it can't run, rather than filling in a number.</p>
              </Reveal>
              <Reveal as="li" delay={270} className="ig-step">
                <figure>
                  <svg viewBox="0 0 300 200" role="img" aria-label="Illustration: the Trust Score scale from 0 to 100">
                    <rect width="300" height="200" fill="#F77737"/>
                    <rect width="300" height="200" fill="url(#seeds)"/>
                    <circle cx="150" cy="100" r="74" fill="#2B1140"/>
                    <g transform="rotate(-90 150 100)" fill="none" strokeWidth="10">
                      <circle cx="150" cy="100" r="54" stroke="rgba(255,255,255,0.12)"/>
                      <circle cx="150" cy="100" r="54" stroke="#FF6B5B" strokeDasharray="132.72 206.57"/>
                      <circle cx="150" cy="100" r="54" stroke="#F2B84D" strokeDasharray="98.79 240.50" strokeDashoffset="-135.72"/>
                      <circle cx="150" cy="100" r="54" stroke="#00D4AA" strokeDasharray="98.79 240.50" strokeDashoffset="-237.50"/>
                    </g>
                    <text x="150" y="106" textAnchor="middle" fill="#FFFFFF" fontFamily="Archivo, Arial, sans-serif" fontSize="22" fontWeight="800" letterSpacing="-1">0–100</text>
                  </svg>
                </figure>
                <span className="ig-step-num">STEP 4</span>
                <h3>One Trust Score</h3>
                <p>A score from 0 to 100 with a verdict, a one-line summary, and a full breakdown you can report if it looks wrong.</p>
              </Reveal>
            </ol>
          </div>
        </section>

        {/* ========================================================== PRICING */}
        <section className="ig-block ig-on-lime" id="pricing">
          <div className="ig-wrap">
            <div className="ig-pricing-head">
              <h2 className="ig-pricing-title ig-display">Pricing</h2>
              <div className="ig-pricing-side">
                <span className="ig-ask">How much?</span>
                <p>Checking a creator is free. Plans for creators and brands are on the roadmap. Their prices below are proposals, not live offers yet.</p>
              </div>
            </div>

            <div className="ig-plans">
              <Reveal as="article" delay={0} className="ig-plan ig-plan-featured">
                <div className="ig-plan-top"><span className="ig-plan-name">Everyone</span><span className="ig-plan-state ig-state-live">LIVE NOW</span></div>
                <div className="ig-plan-price">
                  <div className="ig-price">Rs 0 <small>forever</small></div>
                  <p className="ig-plan-for">For anyone about to trust a creator's advice, product or offer.</p>
                </div>
                <ul>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#00D4AA"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#2B1140" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Full four-check Trust Score</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#00D4AA"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#2B1140" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Plain-English breakdown of every check</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#00D4AA"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#2B1140" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Scan history on your dashboard</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#00D4AA"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#2B1140" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Report a score you disagree with</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#00D4AA"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#2B1140" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Chrome extension for Instagram</li>
                </ul>
                <a className="ig-pill ig-pill-gradient" href="#scan">Start a scan</a>
              </Reveal>

              <Reveal as="article" delay={90} className="ig-plan">
                <div className="ig-plan-top"><span className="ig-plan-name">Creator</span><span className="ig-plan-state ig-state-soon">COMING SOON</span></div>
                <div className="ig-plan-price">
                  <div className="ig-price">Rs 999 <small>/ month</small></div>
                  <p className="ig-plan-for">For influencers who want to prove their audience is real.</p>
                </div>
                <ul>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Everything in Everyone</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Shareable Trust Badge certificate</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Audience authenticity report</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Tips to raise your score</li>
                </ul>
                <button className="ig-pill ig-pill-outline-dark" type="button" disabled>Coming soon</button>
              </Reveal>

              <Reveal as="article" delay={180} className="ig-plan">
                <div className="ig-plan-top"><span className="ig-plan-name">Brand &amp; Agency</span><span className="ig-plan-state ig-state-soon">COMING SOON</span></div>
                <div className="ig-plan-price">
                  <div className="ig-price">Rs 4,999 <small>/ month</small></div>
                  <p className="ig-plan-for">For brands vetting influencers before paying them.</p>
                </div>
                <ul>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Everything in Everyone</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>Compare influencers side by side</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>PDF and CSV reports</li>
                  <li><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#833AB4"/><path d="M5.5 10 L8.6 13 L14.5 7" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>API access for your own tools</li>
                </ul>
                <button className="ig-pill ig-pill-outline-dark" type="button" disabled>Coming soon</button>
              </Reveal>
            </div>
            <p className="ig-pricing-note">Creator and Brand plans follow the user roles in the project scope. Prices shown are proposals for review.</p>
          </div>
        </section>

        {/* ============================================================== FAQ */}
        <section className="ig-block ig-on-indigo" id="faq">
          <div className="ig-wrap ig-faq-grid">
            <div className="ig-faq-side">
              <h2 className="ig-faq-title ig-display">Good<br/>questions</h2>
              <p>Straight answers about what TrustLens checks, what it doesn't, and where every number comes from.</p>
            </div>
            <div className="ig-faq-list">
              <Reveal as="details" delay={0} open>
                <summary>Is TrustLens free?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>Yes. Scanning any public Instagram account is free. Plans for creators and brands are planned, not live.</p>
              </Reveal>
              <Reveal as="details" delay={50}>
                <summary>Where does the data come from?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>From the public profile itself: follower counts, recent posts and captions, fetched live at the moment you scan. TrustLens never asks for anyone's login.</p>
              </Reveal>
              <Reveal as="details" delay={100}>
                <summary>Does it check every one of an account's followers?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>No, and we say so plainly. The live model judges the account's own profile. Instagram blocks bulk access to follower lists, so the follower-network clustering method runs on a labelled research dataset instead.</p>
              </Reveal>
              <Reveal as="details" delay={150}>
                <summary>Is all of it AI?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>Two checks are trained AI models: fake accounts and misinformation. Engagement and credentials are transparent rules, and the Trust Score is a published formula. Each one is labelled on your results page.</p>
              </Reveal>
              <Reveal as="details" delay={200}>
                <summary>What if I think a score is wrong?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>Report it from the results page. A reviewer decides within 48 hours, and the decision, with any corrected score, appears on your dashboard.</p>
              </Reveal>
              <Reveal as="details" delay={250}>
                <summary>Does it understand Urdu?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>Yes. The misinformation model was trained on English and Urdu text, including a category dedicated to Urdu misinformation.</p>
              </Reveal>
              <Reveal as="details" delay={300}>
                <summary>Can it check private accounts?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>No. TrustLens only analyses public accounts.</p>
              </Reveal>
              <Reveal as="details" delay={350}>
                <summary>Is there a browser extension?<span className="ig-plus" aria-hidden="true"></span></summary>
                <p>Yes. The Chrome extension adds a TrustLens badge to Instagram posts as you scroll, using the same models as this site.</p>
              </Reveal>
            </div>
          </div>
        </section>

        {/* ============================================================== CTA (real) */}
        <section className="ig-block ig-on-lime" id="scan">
          <div className="ig-wrap ig-cta-grid">
            <h2 className="ig-cta-title ig-display">Your<br/>turn.</h2>
            <form className="ig-cta-form" onSubmit={handleScan} noValidate>
              <label htmlFor="scan-username">Paste any public Instagram username or profile link</label>
              <div className="ig-cta-row">
                <input
                  className="ig-cta-input"
                  id="scan-username"
                  name="username"
                  type="text"
                  placeholder="@instagram_username"
                  autoComplete="off"
                  spellCheck="false"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); setMessage('') }}
                />
                <button className="ig-pill ig-pill-indigo" type="submit" disabled={authLoading}>
                  Start a scan
                </button>
              </div>
              {message
                ? <p className="ig-cta-msg" role="alert">{message}</p>
                : (
                  <p className="ig-cta-note">
                    {user
                      ? <>Signed in as <strong>{user.full_name}</strong>. The result saves to your dashboard.</>
                      : <>You'll create a free account first. Your scan starts the moment it's ready.</>}
                  </p>
                )}
            </form>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  )
}

export default Landing
