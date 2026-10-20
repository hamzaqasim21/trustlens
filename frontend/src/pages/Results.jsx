import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import PageShell from '../components/site/PageShell'
import ScoreRing from '../components/site/ScoreRing'
import Reveal from '../components/site/Reveal'
import DisputePanel from '../components/DisputePanel'
import { ReportActions } from '../components/ResultExtras'
import { useAuth } from '../context/AuthContext'
import { getSavedResult } from '../api/trustlens'
import { scanPath } from '../lib/scanFlow'
import { formatDateTime, toneFor, toneFromColor } from '../lib/verdict'
import './Results.css'

// How many texts the AI labelled "financial scam" without any concrete scam
// wording to back it up. Those labels are unreliable on promotional captions
// (see backend/misinfo_assessment.py) and are not counted in the score, but
// the page says so openly rather than hiding that the AI raised them.
function uncorroboratedScamLabels(sources) {
  return (sources || []).filter(
    (s) => s.status === 'success' && s.model_category === 'financial_scam' && !s.corroborated,
  ).length
}

// ---- Plain-language interpretation helpers ----
// These translate real computed numbers into a sentence a non-technical
// reader can follow. The thresholds mirror the same logic the backend's
// own rule-based fallback uses (data_ingestion / fake_follower.py), so
// nothing here is invented — it's the same reasoning, just written out.

function describeFollowRatio(ratio, followersCount) {
  if (ratio >= 5) {
    return `This account follows very few people compared to its ${followersCount.toLocaleString()} followers (about ${Math.round(ratio).toLocaleString()} followers for every account it follows). That lopsided ratio is typical of a genuinely popular account; bought followers usually don't produce it.`
  }
  if (ratio >= 0.5) {
    return `This account's ratio of followers to accounts it follows is fairly ordinary, not a strong signal either way.`
  }
  return `This account follows more people than follow it back, which shows up more often on newer or less-established accounts. Not automatically suspicious, but worth weighing alongside the other checks here.`
}

function describeEngagementRate(rate, benchmark, tier) {
  const relation = rate >= benchmark * 1.5 ? 'well above' : rate >= benchmark ? 'at or above' : rate >= benchmark * 0.5 ? 'somewhat below' : 'far below'
  return `On average, ${rate}% of this account's followers interact with each post. For an account this size (the "${tier}" tier), a typical rate is around ${benchmark}%, so this account sits ${relation} what's normal for its size.`
}

// True when no comment numbers can be trusted: the creator turned comments
// off (the backend marks it), or, on scans saved before that marker existed,
// every recent post shows exactly zero comments.
function commentsUnavailable(result) {
  if (result.engagement_analysis?.comments_off) return true
  const posts = result.engagement_data?.posts || []
  return posts.length >= 3 && posts.every((p) => !p.comments)
}

function describeLikeCommentRatio(ratio, noComments) {
  if (noComments || ratio === null || ratio === undefined) {
    return 'No comments were visible on any recent post (the creator has turned comments off or restricted them), so likes-per-comment wasn’t judged. Zero comments here is a setting, not a sign of fake engagement.'
  }
  if (ratio > 500) {
    return `For every comment, this account gets about ${Math.round(ratio).toLocaleString()} likes, an unusually extreme gap that can indicate comments aren't organic.`
  }
  return `For every comment, this account gets about ${Math.round(ratio)} likes. Likes naturally far outnumber comments on real accounts, so this on its own isn't a red flag.`
}

// The one-line summary, for anyone who does not want to read four cards.
//
// Every clause is built from a real value in the API response — nothing here
// is written in advance or padded. When a check did not run, it says so rather
// than quietly leaving it out, so a short summary can never imply that more
// was verified than actually was.
function buildSummary(result) {
  const ff = result.fake_follower_analysis
  const eng = result.engagement_analysis
  const misinfo = result.misinformation_analysis
  const misinfoSources = result.misinformation_sources || []
  const cred = result.credential_analysis
  const verdict = result.trust_score.verdict

  const opening = verdict === 'Trusted' ? 'looks genuine'
    : verdict === 'Moderate Risk' ? 'is a mixed picture'
    : 'looks risky'

  const parts = []

  // The model judges the account itself, not its followers — the wording
  // says exactly that.
  const genuine = Math.round((100 - ff.bot_percentage) * 10) / 10
  parts.push(`the account itself is ${genuine}% likely genuine`)

  if (eng.engagement_score === null || eng.engagement_score === undefined) {
    parts.push("engagement couldn't be measured (no posts could be read)")
  } else {
    parts.push(`${String(eng.status).toLowerCase()} engagement (${eng.engagement_rate}%)`)
  }

  if (misinfo && misinfo.status === 'success') {
    const checked = misinfoSources.length
    const scope = `${checked} text${checked === 1 ? '' : 's'}`
    if (misinfo.misinformation_flag) {
      const where = misinfo.source === 'caption' ? 'a caption' : 'the bio'
      parts.push(`${String(misinfo.primary_category).replace(/_/g, ' ')} flagged in ${where} (${scope} checked)`)
    } else {
      parts.push(`no misinformation across ${scope} checked`)
    }
  } else {
    parts.push('no bio or caption text was available to check')
  }

  // Only mentioned when the bio actually claims something, since "no
  // credentials claimed" is the normal case and not worth a clause.
  if (cred && cred.claims_found && cred.claims_found.length) {
    const st = cred.verification?.status
    const how = st === 'found_active' ? 'found in an official register'
      : st === 'found_inactive' ? 'license not active in the register'
      : st === 'not_found' ? 'not found in the doctor registers'
      : 'not checkable'
    parts.push(`bio claims ${cred.claims_found.join(', ')} (${how})`)
  }

  const last = parts.pop()
  return `@${result.username} ${opening}: ${parts.join(', ')}, and ${last}.`
}

// ---------------------------------------------------------------------------
// Module metadata, in the order the backend weighs them.
// ---------------------------------------------------------------------------
const MODULES = {
  fake_follower: { title: 'Account authenticity', kind: 'AI MODEL', kindTone: 'ink', swatch: 'rs-sw-purple' },
  engagement: { title: 'Engagement', kind: 'RULES', kindTone: 'outline', swatch: 'rs-sw-blue' },
  misinformation: { title: 'Misinformation', kind: 'AI + RULES', kindTone: 'ink', swatch: 'rs-sw-pink' },
  credential: { title: 'Credential claims', kind: 'RULES', kindTone: 'outline', swatch: 'rs-sw-orange' },
}
const MODULE_ORDER = ['fake_follower', 'engagement', 'misinformation', 'credential']

// The real 0-100 score each module contributed. Newer scans carry these
// from the backend; older saved scans are rebuilt from the same fields the
// backend itself uses, so the maths is identical either way.
function moduleScores(result) {
  if (result.trust_score.module_scores) return result.trust_score.module_scores
  const out = { fake_follower: Math.max(0, 100 - result.fake_follower_analysis.bot_percentage) }
  const eng = result.engagement_analysis.engagement_score
  if (eng !== null && eng !== undefined) out.engagement = eng
  if (result.misinformation_analysis?.status === 'success') out.misinformation = Math.max(0, 100 - result.misinformation_analysis.risk_score)
  const cred = result.credential_analysis?.confidence_score
  if (cred !== null && cred !== undefined) out.credential = cred
  return out
}

// ---------------------------------------------------------------------------
// "Where the score came from": one bar, one segment per check that ran.
// Each segment is as wide as that check's weight this scan; the filled part
// is how much of that weight the account earned (weight × module score).
// Added up, the filled parts are the Trust Score.
// ---------------------------------------------------------------------------
function ScoreComposition({ result, onPick }) {
  const weights = result.trust_score.weights_used
  if (!weights) return null
  const scores = moduleScores(result)
  const rows = MODULE_ORDER.filter((m) => m in weights).map((m) => ({
    key: m,
    weight: weights[m],
    score: Math.round((scores[m] ?? 0) * 10) / 10,
    points: Math.round(((weights[m] * (scores[m] ?? 0)) / 100) * 10) / 10,
  }))
  const weighted = Math.round(rows.reduce((s, r) => s + (r.weight * r.score) / 100, 0) * 10) / 10
  const final = result.trust_score.trust_score
  const capped = result.fake_follower_analysis.bot_percentage >= 85 && final < weighted

  return (
    <div className="rs-comp">
      <div className="rs-comp-bar" role="img" aria-label={`Score composition: ${rows.map((r) => `${MODULES[r.key].title} ${r.points} of ${r.weight} points`).join(', ')}`}>
        {rows.map((r) => (
          <button
            type="button"
            key={r.key}
            className={`rs-comp-seg ${MODULES[r.key].swatch}`}
            style={{ flexBasis: `${r.weight}%` }}
            onClick={() => onPick(r.key)}
            title={`${MODULES[r.key].title}: ${r.points} of ${r.weight} possible points`}
          >
            <span className="rs-comp-fill" style={{ width: `${Math.min(100, r.score)}%` }} />
            <span className="rs-comp-seg-label">{r.points}</span>
          </button>
        ))}
      </div>
      <div className="rs-comp-legend">
        {rows.map((r) => (
          <button type="button" key={r.key} className="rs-comp-item" onClick={() => onPick(r.key)}>
            <span className={`rs-comp-dot ${MODULES[r.key].swatch}`} aria-hidden="true" />
            <span className="rs-comp-name">{MODULES[r.key].title}</span>
            <span className="rs-comp-math tl-mono">{r.weight}% × {r.score} = <strong>{r.points}</strong></span>
          </button>
        ))}
        <div className="rs-comp-total">
          <span>Added up</span>
          <strong className="tl-mono">{weighted}</strong>
        </div>
      </div>
      {capped && (
        <p className="tl-alert tl-alert-bad rs-comp-note">
          The fake-account model is {result.fake_follower_analysis.bot_percentage}% sure this account itself is fake, which
          triggers the kill switch: the score is capped at 15 no matter how the other checks came out.
        </p>
      )}
      <p className="rs-comp-foot">
        Weights change from scan to scan: a check that couldn’t run (no text to read, no credential claimed) hands its
        share to the checks that did, so the weights always add up to 100% of real signal.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Module cards
// ---------------------------------------------------------------------------
function ModuleCard({ id, value, sub, chip, chipTone, weight, inactive, onOpen }) {
  const meta = MODULES[id]
  return (
    <button type="button" className={`rs-mod tl-card tl-card-hover ${inactive ? 'is-inactive' : ''}`} onClick={() => onOpen(id)}>
      <span className={`rs-mod-band ${meta.swatch}`} aria-hidden="true" />
      <span className="rs-mod-top">
        <span className="rs-mod-title">{meta.title}</span>
        <span className={`tl-chip tl-chip-plain ${meta.kindTone === 'ink' ? 'tl-chip-ink' : 'tl-chip-outline'}`}>{meta.kind}</span>
      </span>
      <span className="rs-mod-value">{value}</span>
      <span className="rs-mod-sub">{sub}</span>
      <span className="rs-mod-foot">
        {chip ? <span className={`tl-chip tl-chip-${chipTone}`}>{chip}</span> : <span />}
        <span className="rs-mod-weight tl-mono">{inactive ? 'Not scored' : `${weight}% of score`}</span>
      </span>
      <span className="rs-mod-more">See how this was worked out →</span>
    </button>
  )
}

// What the Credential Extractor actually managed to check. A doctor claim is
// looked up in the PMDC (Pakistan) and US NPI registers; anything else has no
// free public register, so it is shown but not scored (credential_extractor.py).
function credentialCheck(cred) {
  const v = cred?.verification || {}
  const reg = v.registry || 'official'
  switch (v.status) {
    case 'found_active':
      return { chip: 'In official register', tone: 'ok', scored: true,
        sub: `found in the ${reg} register, license active` }
    case 'found_inactive':
      return { chip: 'License not active', tone: 'bad', scored: true,
        sub: `found in the ${reg} register, but the license isn't active` }
    case 'not_found':
      return { chip: 'Not in register', tone: 'bad', scored: true,
        sub: 'no registered doctor with this name in PMDC or the US NPI register' }
    case 'no_name':
      return { chip: 'Not checkable', tone: 'neutral', scored: false,
        sub: 'no full name to look up in a register, so not scored' }
    case 'unavailable':
      return { chip: 'Not checked', tone: 'neutral', scored: false,
        sub: "the registers couldn't be reached, so not scored" }
    default:
      return { chip: 'Not checkable', tone: 'neutral', scored: false,
        sub: 'no public register exists for this claim, so not scored' }
  }
}

function ModuleCards({ result, onOpen }) {
  const ff = result.fake_follower_analysis
  const eng = result.engagement_analysis
  const misinfo = result.misinformation_analysis
  const sources = result.misinformation_sources || []
  const cred = result.credential_analysis
  const weights = result.trust_score.weights_used || {}
  const setAside = uncorroboratedScamLabels(sources)

  const engMeasured = eng.engagement_score !== null && eng.engagement_score !== undefined
  const misinfoRan = misinfo && misinfo.status === 'success'
  const credClaimed = cred && cred.claims_found && cred.claims_found.length > 0
  const credCheck = credentialCheck(cred)

  return (
    <div className="rs-mods">
      <Reveal delay={0}>
        <ModuleCard
          id="fake_follower"
          value={`${Math.round((100 - ff.bot_percentage) * 10) / 10}%`}
          sub="likely genuine, judged from the account’s own profile"
          chip={ff.verdict}
          chipTone={toneFromColor(ff.color)}
          weight={weights.fake_follower}
          onOpen={onOpen}
        />
      </Reveal>
      <Reveal delay={80}>
        <ModuleCard
          id="engagement"
          value={engMeasured ? `${eng.engagement_rate}%` : 'n/a'}
          sub={engMeasured ? `engagement rate, ${eng.tier} tier (normal is about ${eng.benchmark}%)` : 'Instagram returned no posts, so this wasn’t measured'}
          chip={engMeasured ? eng.status : null}
          chipTone={toneFromColor(eng.color)}
          weight={weights.engagement}
          inactive={!engMeasured}
          onOpen={onOpen}
        />
      </Reveal>
      <Reveal delay={160}>
        <ModuleCard
          id="misinformation"
          value={misinfoRan ? (misinfo.misinformation_flag ? 'Flagged' : 'Clear') : 'n/a'}
          sub={
            misinfoRan
              ? (misinfo.misinformation_flag
                ? `${String(misinfo.primary_category).replace(/_/g, ' ')} in ${misinfo.source === 'caption' ? 'a caption' : 'the bio'} (${sources.length} texts read)`
                : `nothing concerning in ${sources.length} text${sources.length === 1 ? '' : 's'}${setAside ? `; ${setAside} unsupported AI “scam” label${setAside === 1 ? '' : 's'} set aside` : ''}`)
              : 'No bio or caption text to read'
          }
          chip={misinfoRan ? (misinfo.misinformation_flag ? 'Flagged' : 'Credible') : null}
          chipTone={misinfoRan ? (misinfo.misinformation_flag ? 'bad' : 'ok') : 'neutral'}
          weight={weights.misinformation}
          inactive={!misinfoRan}
          onOpen={onOpen}
        />
      </Reveal>
      <Reveal delay={240}>
        <ModuleCard
          id="credential"
          value={credClaimed ? cred.claims_found.join(', ') : 'None'}
          sub={credClaimed ? credCheck.sub : 'no professional credential claimed in the bio'}
          chip={credClaimed ? credCheck.chip : null}
          chipTone={credClaimed ? credCheck.tone : 'neutral'}
          weight={weights.credential}
          inactive={!credClaimed || !credCheck.scored}
          onOpen={onOpen}
        />
      </Reveal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Full breakdown, one block per module (same content as before, new look)
// ---------------------------------------------------------------------------
function BreakdownModule({ id, title, score, weight, badgeText, badgeTone, explanation, metrics, inactiveNote }) {
  return (
    <section className="rs-bd-mod" id={`bd-${id}`}>
      <div className="rs-bd-head">
        <span className={`rs-bd-sw ${MODULES[id].swatch}`} aria-hidden="true" />
        <h3>{title}</h3>
        <span className="rs-bd-weight tl-mono">{inactiveNote ? '0% this scan' : `${weight}% of Trust Score`}</span>
      </div>

      {inactiveNote ? (
        <p className="rs-bd-note">{inactiveNote}</p>
      ) : (
        <>
          <div className="rs-bd-scoreline">
            <div className="rs-bd-track"><div className={`rs-bd-fill ${MODULES[id].swatch}`} style={{ width: `${score}%` }} /></div>
            <span className="rs-bd-score tl-mono">{score}/100</span>
            {badgeText && <span className={`tl-chip tl-chip-${badgeTone}`}>{badgeText}</span>}
          </div>
          {explanation && <p className="rs-bd-text">{explanation}</p>}
          {metrics?.length > 0 && (
            <details className="rs-bd-raw">
              <summary>Show the raw numbers behind this</summary>
              <dl>
                {metrics.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </>
      )}
    </section>
  )
}

function ScoreBreakdown({ result }) {
  const ff = result.fake_follower_analysis
  const eng = result.engagement_analysis
  const misinfo = result.misinformation_analysis
  const misinfoSources = result.misinformation_sources || []
  const cred = result.credential_analysis
  const followersCount = result.raw_profile_data.followers

  // Real weights the backend actually used for this scan — always sums to
  // 100%, since unused modules' weight is redistributed onto whichever
  // modules DID apply (see trust_score.py). Never hardcode these on the
  // frontend; they legitimately change scan to scan.
  const weights = result.trust_score.weights_used || {}
  const misinfoApplicable = 'misinformation' in weights
  const credentialApplicable = 'credential' in weights
  const engagementMeasured = 'engagement' in weights

  const ffScore = Math.round(100 - ff.bot_percentage)
  const misinfoScore = misinfoApplicable ? Math.round(100 - misinfo.risk_score) : null
  const setAside = uncorroboratedScamLabels(misinfoSources)

  return (
    <div className="rs-bd">
      <BreakdownModule
        id="fake_follower"
        title="Account authenticity (fake-account model)"
        score={ffScore}
        weight={weights.fake_follower ?? 0}
        badgeText={ff.verdict}
        badgeTone={toneFromColor(ff.color)}
        explanation={
          'A trained model judges whether this account itself looks like a fake or spam account, from its own profile ' +
          '(followers, following, posts, photo, bio, username). It does not look at the individual followers. ' +
          describeFollowRatio(ff.follower_follow_ratio, followersCount)
        }
        metrics={[
          ['Fake-account likelihood', `${ff.bot_percentage}%`],
          ['Follower-to-following ratio', ff.follower_follow_ratio],
          ['Posts per follower', ff.posts_per_follower],
          ['Has bio text', ff.has_bio ? 'Yes' : 'No'],
        ]}
      />

      <BreakdownModule
        id="engagement"
        title="Engagement analysis"
        score={eng.engagement_score}
        weight={weights.engagement ?? 0}
        badgeText={eng.status}
        badgeTone={toneFromColor(eng.color)}
        explanation={engagementMeasured ? `${describeEngagementRate(eng.engagement_rate, eng.benchmark, eng.tier)} ${describeLikeCommentRatio(eng.like_comment_ratio, commentsUnavailable(result))}` : null}
        metrics={engagementMeasured ? [
          ['Engagement rate', `${eng.engagement_rate}%`],
          ['Benchmark for its size', `${eng.benchmark}% (${eng.tier} tier)`],
          ['Like-to-comment ratio', commentsUnavailable(result) ? 'Not judged (comments off)' : eng.like_comment_ratio],
        ] : []}
        inactiveNote={engagementMeasured ? null :
          'Instagram didn’t return any posts for this account on this scan, so there was nothing to measure. Its weight went to the checks that did run, rather than treating “no data” as “no engagement”.'}
      />

      <BreakdownModule
        id="misinformation"
        title="Misinformation (bio + captions)"
        score={misinfoScore}
        weight={weights.misinformation ?? 0}
        badgeText={misinfoApplicable ? (misinfo.misinformation_flag ? 'Flagged' : 'Credible') : null}
        badgeTone={misinfoApplicable && misinfo.misinformation_flag ? 'bad' : 'ok'}
        explanation={misinfoApplicable ? (
          `Checked ${misinfoSources.length} piece${misinfoSources.length === 1 ? '' : 's'} of text (bio + recent post captions) with an AI classifier, ` +
          'cross-checked against rule-based scam patterns (such as "guaranteed returns", impossible claims and disguised links). ' +
          (misinfo.misinformation_flag
            ? `The worst result came from ${misinfo.source === 'caption' ? 'a post caption' : 'the bio'}: "${misinfo.text_preview}", counted as "${misinfo.primary_category.replace(/_/g, ' ')}". ${misinfo.note || ''}`
            : 'Nothing concerning was counted.') +
          (setAside > 0
            ? ` The AI also labelled ${setAside} ${setAside === 1 ? 'text' : 'texts'} "financial scam" without any concrete scam wording in ${setAside === 1 ? 'it' : 'them'}; ` +
              "those labels weren't counted, because that part of the AI was trained on SMS spam and mistakes ordinary adverts for scams."
            : '')
        ) : null}
        metrics={misinfoApplicable ? [
          ['Worst result source', misinfo.source === 'caption' ? 'Post caption' : 'Bio'],
          ['Counted as', misinfo.primary_category?.replace(/_/g, ' ')],
          ['AI label on its own', misinfo.model_category?.replace(/_/g, ' ') ?? 'n/a'],
          ['Scam patterns found', misinfo.red_flags?.length ? misinfo.red_flags.map((f) => f.title).join(', ') : 'none'],
          ['Risk score', `${misinfo.risk_score}/100`],
          ...misinfoSources
            .filter((s) => s.status === 'success' && s.misinformation_flag && s !== misinfo)
            .map((s) => [`Also counted (${s.source})`, `"${s.text_preview}", ${s.primary_category.replace(/_/g, ' ')}`]),
        ] : []}
        inactiveNote={misinfoApplicable ? null :
          'This profile had no bio and no post captions to check, so its weight went to the checks that did run rather than guessing a score. (Speech in reels is the one input from the scope document that isn’t wired in yet.)'}
      />

      <BreakdownModule
        id="credential"
        title="Credential claims (bio)"
        score={credentialApplicable ? cred.confidence_score : null}
        weight={weights.credential ?? 0}
        badgeText={credentialApplicable ? credentialCheck(cred).chip : null}
        badgeTone={credentialApplicable ? credentialCheck(cred).tone : 'neutral'}
        explanation={credentialApplicable
          ? `The bio claims: ${cred.claims_found.join(', ')}. ${cred.verdict}. A doctor claim is looked up by name in the PMDC (Pakistan) and US NPI public registers. A match shows that a registered doctor has this name; it can't prove this account belongs to them.${cred.unchecked_note ? ' ' + cred.unchecked_note : ''}`
          : null}
        metrics={credentialApplicable ? [
          ['Claims found', cred.claims_found.join(', ')],
          ['Register result', credentialCheck(cred).chip],
          ...(cred.verification?.matches?.[0] ? [['Registration', `${cred.verification.matches[0].registration_no} (${cred.verification.matches[0].status})`]] : []),
          ['Credential score', `${cred.confidence_score}/100`],
        ] : []}
        inactiveNote={credentialApplicable ? null : (cred && cred.claims_found && cred.claims_found.length
          ? `The bio claims ${cred.claims_found.join(', ')}, but ${credentialCheck(cred).sub}. Its weight went to the checks that did run rather than guessing a score.`
          : 'No professional credential claims (such as "Dr.", "CFA", "MBBS") were found in the bio, so its weight went to the checks that did run rather than guessing a score.')}
      />

      <p className="rs-bd-foot">
        Deepfake Scanner and Follower Spike Detection are in the original scope document’s weight table but aren’t built
        yet. They’re not part of this calculation at all, not even at a placeholder value.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Scan log: what was read, ticking in one line at a time
// ---------------------------------------------------------------------------
function ScanLog({ result }) {
  const rows = [
    // "Follower count", not "followers analyzed": the scan reads the count
    // from the profile — it never inspects the followers themselves.
    ['Follower count', result.raw_profile_data.followers.toLocaleString()],
    ['Following', result.raw_profile_data.following?.toLocaleString?.() ?? 'n/a'],
    ['Posts on profile', result.raw_profile_data.posts?.toLocaleString?.() ?? 'n/a'],
    ['Fake-account likelihood', `${result.fake_follower_analysis.bot_percentage}%`],
    ['Texts read for misinformation', String((result.misinformation_sources || []).length)],
    ['Instagram verification', result.is_verified ? 'Verified account' : 'Not verified'],
  ]
  const [shown, setShown] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setShown((n) => (n < rows.length ? n + 1 : n)), 260)
    return () => clearInterval(timer)
  }, [rows.length])

  return (
    <div className="rs-log tl-card-plum">
      <div className="rs-log-head">
        <span className="tl-eyebrow">Scan log</span>
        <span className="rs-log-dot" aria-hidden="true" />
      </div>
      <ul>
        {rows.map(([label, value], i) => (
          <li key={label} className={i < shown ? 'is-in' : ''}>
            <span className="rs-log-tick" aria-hidden="true">{i < shown ? '✓' : ''}</span>
            <span className="rs-log-label">{label}</span>
            <span className="rs-log-value tl-mono">{i < shown ? value : ''}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Where the score sits on the 0-100 scale
// ---------------------------------------------------------------------------
function ScaleMarker({ score }) {
  const pos = Math.max(0, Math.min(100, score))
  return (
    <div className="rs-scale" aria-hidden="true">
      <div className="rs-scale-bar">
        <span className="rs-scale-bad" />
        <span className="rs-scale-warn" />
        <span className="rs-scale-ok" />
        <span className="rs-scale-pin" style={{ left: `${pos}%` }} />
      </div>
      <div className="rs-scale-labels tl-mono">
        <span>0 High risk</span>
        <span>40 Moderate</span>
        <span>70 Trusted 100</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------
function ResultView({ result }) {
  const navigate = useNavigate()
  const [showBreakdown, setShowBreakdown] = useState(false)
  const breakdownRef = useRef(null)

  const verdict = result.trust_score.verdict
  const tone = toneFor(verdict)
  const score = result.trust_score.trust_score
  const correction = result.correction
  const when = result.scanned_at ? formatDateTime(result.scanned_at) : 'just now'

  function openModule(id) {
    setShowBreakdown(true)
    // Wait a frame for the breakdown to render before scrolling to it.
    requestAnimationFrame(() => {
      const el = document.getElementById(`bd-${id}`) || breakdownRef.current
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  return (
    <>
      <section className={`rs-hero rs-tone-${tone}`}>
        <div className="tl-pagehead-blob" aria-hidden="true" />
        <div className="tl-wrap rs-hero-grid">
          <div className="rs-hero-copy">
            <span className="tl-eyebrow">Scan result · {when}</span>

            <div className="rs-who">
              <span className="tl-avatar tl-avatar-lg" aria-hidden="true">{result.username.charAt(0).toUpperCase()}</span>
              <div>
                <div className="rs-who-name">
                  {result.full_name || result.username}
                  {result.is_verified && <span className="tl-chip tl-chip-ink tl-chip-plain">Verified</span>}
                </div>
                <a
                  className="rs-who-handle tl-mono"
                  href={`https://www.instagram.com/${result.username}/`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  @{result.username} ↗
                </a>
              </div>
            </div>

            <h1 className="tl-display rs-verdict">{verdict}.</h1>

            <div className="rs-summary">
              <span className="rs-summary-label tl-mono">In one line</span>
              <p>{buildSummary(result)}</p>
            </div>

            {correction && (
              <p className="tl-alert tl-alert-grad rs-correction">
                <span>
                  <strong>Corrected after review.</strong> A reviewer upheld a report on this scan and set the score to{' '}
                  <strong>{correction.trust_score} ({correction.verdict})</strong>. The original result the models gave is shown
                  below, unchanged.
                </span>
              </p>
            )}

            <div className="rs-actions">
              <button className="tl-btn tl-btn-grad" onClick={() => openModule('fake_follower')}>See the full breakdown</button>
              <button className="tl-btn tl-btn-outline" onClick={() => navigate('/comparison', { state: { a: result.username } })}>Compare</button>
              <button className="tl-btn tl-btn-soft" onClick={() => navigate(scanPath(result.username))}>Re-scan</button>
            </div>
            <ReportActions result={result} />
          </div>

          <div className="rs-hero-side">
            <ScoreRing score={score} tone={tone} size={300} />
            <ScaleMarker score={score} />
          </div>
        </div>
      </section>

      <section className="tl-band tl-band-tint rs-checks">
        <div className="tl-wrap">
          <div className="rs-sec-head">
            <div>
              <span className="tl-eyebrow">Four checks</span>
              <h2 className="tl-display rs-sec-title">Where the score<br />came from.</h2>
            </div>
            <ScanLog result={result} />
          </div>

          <Reveal><ScoreComposition result={result} onPick={openModule} /></Reveal>
          <ModuleCards result={result} onOpen={openModule} />
        </div>
      </section>

      <section className="tl-band rs-breakdown" ref={breakdownRef}>
        <div className="tl-wrap-narrow">
          <div className="rs-bd-intro">
            <span className="tl-eyebrow">The working</span>
            <h2 className="tl-display rs-sec-title">How it was<br />calculated.</h2>
            <p className="tl-lede">
              Every number here comes straight from the checks that ran on this profile. Nothing is estimated or made up for display.
            </p>
            <button className="tl-btn tl-btn-outline" onClick={() => setShowBreakdown((v) => !v)} aria-expanded={showBreakdown}>
              {showBreakdown ? 'Hide the breakdown' : 'Show the breakdown'}
            </button>
          </div>
          {showBreakdown && <ScoreBreakdown result={result} />}
        </div>
      </section>

      <section className="tl-band tl-band-lav rs-next">
        <div className="tl-wrap rs-next-grid">
          <div className="rs-next-copy">
            <span className="tl-eyebrow">What next</span>
            <h2 className="tl-display rs-sec-title">Keep<br />looking.</h2>
            <div className="rs-next-links">
              <Link to="/scan" className="rs-next-link tl-card tl-card-hover">
                <strong>Scan another profile</strong><span>Check someone else in about 20 seconds</span>
              </Link>
              <Link to="/comparison" state={{ a: result.username }} className="rs-next-link tl-card tl-card-hover">
                <strong>Compare side by side</strong><span>Put @{result.username} against another account</span>
              </Link>
              <Link to="/dashboard" className="rs-next-link tl-card tl-card-hover">
                <strong>Your scan history</strong><span>Every scan, and any reports you’ve filed</span>
              </Link>
            </div>
          </div>
          <DisputePanel
            scanId={result.scan_id}
            username={result.username}
            scannedWhileLoggedIn={Boolean(result.scan_owned)}
            appealStatus={result.appeal_status}
          />
        </div>
      </section>
    </>
  )
}

function Results() {
  const location = useLocation()
  const [params] = useSearchParams()
  const { user, loading: authLoading, signedOut } = useAuth()
  const stateResult = location.state?.result || null
  const id = params.get('id')
  const [fetched, setFetched] = useState({ id: null, result: null, error: '' })

  // Whenever the URL carries a scan id, re-fetch the saved copy in the
  // background and prefer it once it arrives — router state is only used to
  // paint instantly before that lands. State alone isn't reliable once a
  // scan id exists: a hard reload keeps the browser's OWN history.state from
  // before a report was filed (found live — filing a report, then
  // reloading, kept showing "not yet reported" because of this), and a link
  // from the Dashboard carries no state at all. Costs no RapidAPI quota.
  const needFetch = Boolean(id) && Boolean(user)
  useEffect(() => {
    if (!needFetch) return
    let cancelled = false
    getSavedResult(id)
      .then((r) => { if (!cancelled) setFetched({ id, result: r, error: '' }) })
      .catch((err) => { if (!cancelled) setFetched({ id, result: null, error: err.message || 'Could not open this scan.' }) })
    return () => { cancelled = true }
  }, [needFetch, id])

  const fetchedForThisId = fetched.id === id
  const result = (fetchedForThisId && fetched.result) || stateResult
  const error = fetchedForThisId ? fetched.error : ''
  const stillLoading = !result && !error && (authLoading || needFetch)

  if (!result) {
    if (stillLoading) return <PageShell title="Result" footer={false}><div className="rs-loading"><span className="tl-spinner" /></div></PageShell>
    if (!id) return <Navigate to={user ? '/dashboard' : '/'} replace />
    if (!user) return <Navigate to={signedOut ? '/' : `/login?next=${encodeURIComponent(`/results?id=${id}`)}`} replace />
  }

  if (error) {
    return (
      <PageShell title="Result">
        <section className="tl-band">
          <div className="tl-wrap-narrow">
            <div className="tl-empty">
              <h3>This scan couldn’t be opened</h3>
              <p>{error}</p>
              <Link to="/dashboard" className="tl-btn tl-btn-grad">Back to your dashboard</Link>
            </div>
          </div>
        </section>
      </PageShell>
    )
  }

  if (!result) {
    return <PageShell title="Result" footer={false}><div className="rs-loading"><span className="tl-spinner" /><span>Opening the saved result…</span></div></PageShell>
  }

  return (
    <PageShell title={`@${result.username} · ${result.trust_score.verdict}`} className="rs-page">
      <ResultView key={result.scan_id ?? result.username} result={result} />
    </PageShell>
  )
}

export default Results
