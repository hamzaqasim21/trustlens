import { Link } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import Reveal from '../components/site/Reveal'
import CountUp from '../components/CountUp'
import './About.css'

const STEPS = [
  {
    n: '01', tag: 'Ingest', swatch: 'ab-sw-blue', title: 'Real profile data',
    body: 'The public profile, recent posts, captions and the sound of the newest reels are fetched live the moment you scan. Nothing is typed in by hand, and TrustLens never asks for anyone’s Instagram login.',
  },
  {
    n: '02', tag: 'Analyse', swatch: 'ab-sw-purple', title: 'Four independent checks',
    body: 'Two trained AI models and two sets of transparent rules each look at the account on their own, without knowing what the others found.',
  },
  {
    n: '03', tag: 'Score', swatch: 'ab-sw-pink', title: 'One weighted Trust Score',
    body: 'Every check that ran is weighed into a single 0 to 100 score with a verdict. A check that couldn’t run hands its weight to the ones that did, instead of guessing.',
  },
  {
    n: '04', tag: 'Explain', swatch: 'ab-sw-orange', title: 'Every number, explained',
    body: 'Not just a score: a plain-English reason for each check, the raw numbers behind it, and a way to report it if you think it’s wrong.',
  },
]

// The honest AI-versus-rules picture. This is what the panel is most likely
// to ask about, so the site states it plainly rather than calling it all "AI".
const MODULES = [
  { name: 'Fake-account detection', kind: 'AI model', tone: 'ink', what: 'A trained Random Forest judges whether the account itself looks fake from its own profile.', proof: '95.8% on a held-out test set' },
  { name: 'Misinformation check', kind: 'AI + rules', tone: 'ink', what: 'A fine-tuned XLM-RoBERTa language model reads the bio, the captions and what is said in reels, in English and Urdu, cross-checked against hand-written scam patterns.', proof: '77% on a held-out test set' },
  { name: 'Video-to-Text', kind: 'Pretrained AI', tone: 'outline', what: 'OpenAI’s Whisper speech model listens to the first 45 seconds of the newest reels and writes down what is said, so a scam spoken aloud can be caught. Speech labelled Hindi is written in Urdu script, which the language model reads.', proof: 'Used as-is, not trained by us' },
  { name: 'Engagement analysis', kind: 'Rules', tone: 'outline', what: 'Likes and comments per follower, compared with what’s typical for an account of that size.', proof: 'Transparent formula' },
  { name: 'Credential claims', kind: 'Rules', tone: 'outline', what: 'Finds claims like “Dr.”, “MBBS” or “CFA” in the bio. A doctor claim is looked up by name in the PMDC and US NPI public registers; other claims have no public register, so they are shown but not scored.', proof: 'Pattern matching + official registers' },
  { name: 'Trust Score', kind: 'Formula', tone: 'outline', what: 'A published weighted average of the checks that ran, with a cap when the account itself looks fake.', proof: 'Weights always total 100%' },
]

function About() {
  return (
    <PageShell title="How it works" className="ab-page">
      <section className="tl-pagehead">
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap">
          <span className="tl-eyebrow">How it works</span>
          <h1 className="tl-display tl-pagehead-title">Not a<br /><span className="tl-grad-text">black box.</span></h1>
          <p className="tl-lede tl-pagehead-lede">
            TrustLens doesn’t guess. Every score is built from real data and checks you can inspect, and every one of them
            is labelled for what it is: a trained model, a rule, or a formula. Here’s exactly what happens when you scan a profile.
          </p>
        </div>
      </section>

      <div className="tl-marquee-band" aria-hidden="true">
        <div className="tl-marquee">
          {[0, 1].flatMap((k) =>
            ['Fetch', 'Check', 'Weigh', 'Explain', 'Report', 'Correct'].map((w) => <span key={`${k}-${w}`}>{w}</span>),
          )}
        </div>
      </div>

      <section className="tl-band tl-band-tint">
        <div className="tl-wrap">
          <div className="ab-sec-head">
            <span className="tl-eyebrow">The pipeline</span>
            <h2 className="tl-display ab-sec-title">Four steps,<br />every scan.</h2>
          </div>
          <ol className="ab-steps">
            {STEPS.map((s, i) => (
              <Reveal as="li" key={s.n} delay={i * 90} className="ab-step tl-card tl-card-hover">
                <span className={`ab-step-art ${s.swatch}`} aria-hidden="true"><span>{s.n}</span></span>
                <span className="tl-chip tl-chip-outline">{s.tag}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="tl-band">
        <div className="tl-wrap ab-honest">
          <div className="ab-honest-copy">
            <span className="tl-eyebrow">AI or rules?</span>
            <h2 className="tl-display ab-sec-title">Straight<br />answers.</h2>
            <p className="tl-lede">
              Two of the checks are trained AI models. The rest are transparent rules and a published formula, which is
              exactly what the project scope calls for in those parts. Nothing rule-based is dressed up as AI.
            </p>
            <Link to="/methodology" className="tl-btn tl-btn-outline">See the graph method</Link>
          </div>
          <div className="ab-table tl-card">
            {MODULES.map((m, i) => (
              <Reveal key={m.name} delay={i * 60} className="ab-row">
                <div className="ab-row-top">
                  <strong>{m.name}</strong>
                  <span className={`tl-chip tl-chip-plain ${m.tone === 'ink' ? 'tl-chip-ink' : 'tl-chip-outline'}`}>{m.kind}</span>
                </div>
                <p>{m.what}</p>
                <span className="ab-row-proof tl-mono">{m.proof}</span>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="tl-band tl-band-plum ab-numbers">
        <div className="tl-wrap">
          <span className="tl-eyebrow">Measured, not claimed</span>
          <div className="ab-stats">
            <div>
              <span className="ab-stat-value tl-grad-text"><CountUp value={95.8} decimals={1} duration={1200} />%</span>
              <span className="ab-stat-label">Fake-account model accuracy, on accounts it never saw in training</span>
            </div>
            <div>
              <span className="ab-stat-value tl-grad-text"><CountUp value={77} duration={1200} />%</span>
              <span className="ab-stat-label">Misinformation classifier accuracy, on a held-out test set of 4,640 texts</span>
            </div>
            <div>
              <span className="ab-stat-value tl-grad-text">48h</span>
              <span className="ab-stat-label">For a person to review any score you report</span>
            </div>
          </div>
        </div>
      </section>

      <section className="tl-band tl-band-lav">
        <div className="tl-wrap ab-team">
          <div>
            <span className="tl-eyebrow">Who built it</span>
            <h2 className="tl-display ab-sec-title">A final-year<br />project.</h2>
            <p className="tl-lede">
              Built at the Faculty of Computing and AI, Air University Islamabad, because Pakistan saw more than 13,000
              online fraud complaints in 2024, many of them starting with a creator nobody had checked.
            </p>
          </div>
          <div className="ab-people">
            {[
              ['Hamza Qasim', 'Team'],
              ['Ali Ahmad', 'Team'],
              ['Umar Zubair', 'Team'],
              ['M. Zulfiqar Khan', 'Supervisor'],
            ].map(([name, role], i) => (
              <Reveal key={name} delay={i * 70} className="ab-person tl-card">
                <span className="tl-avatar" aria-hidden="true">{name.split(' ').filter((w) => !w.endsWith('.')).map((w) => w[0]).join('').slice(0, 2)}</span>
                <span><strong>{name}</strong><span>{role}</span></span>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="tl-band ab-cta">
        <div className="tl-wrap ab-cta-inner">
          <h2 className="tl-display ab-cta-title">See it<br /><span className="tl-grad-text">for yourself.</span></h2>
          <Link to="/scan" className="tl-btn tl-btn-grad tl-btn-lg">Scan a profile</Link>
        </div>
      </section>
    </PageShell>
  )
}

export default About
