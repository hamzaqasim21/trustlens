/*
 * content.js — renders the badge and drives one post's analysis.
 *
 * Security note that shaped this whole file: **no innerHTML anywhere.**
 * Everything rendered here is untrusted — the caption comes from a stranger's
 * post, and the explanation comes from a language model that was fed that
 * caption. Building nodes with textContent means a caption containing markup or
 * a script tag is displayed as the characters it is, and can never execute
 * inside instagram.com's origin.
 */
window.TL = window.TL || {};

TL.ui = (function () {
  "use strict";

  const LEVEL_LABEL = {
    danger: "High risk",
    warning: "Warning",
    caution: "Caution",
    clean: "Looks OK",
    unknown: "Not fully checked",
  };

  function el(tag, className, textContent) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textContent !== undefined && textContent !== null) node.textContent = textContent;
    return node;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }

  /**
   * The score ring: an SVG donut with the 0-100 trust score in the middle.
   * The arc length is the score, the colour comes from the badge's level class
   * (see .tl-ring-arc in styles.css), so the number and the colour always agree.
   * A null score (nothing was checked) shows a full grey track with "?", never a
   * misleading zero.
   */
  function scoreRing(score) {
    const size = 46, stroke = 5, r = (size - stroke) / 2;
    const circ = 2 * Math.PI * r;
    const pct = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;

    const svg = svgEl("svg", {
      class: "tl-ring", width: size, height: size,
      viewBox: `0 0 ${size} ${size}`, role: "img",
      "aria-label": score == null ? "Not scored" : `Trust score ${score} of 100`,
    });
    const cx = size / 2;
    svg.appendChild(svgEl("circle", {
      class: "tl-ring-track", cx, cy: cx, r, fill: "none", "stroke-width": stroke,
    }));
    if (score != null) {
      svg.appendChild(svgEl("circle", {
        class: "tl-ring-arc", cx, cy: cx, r, fill: "none", "stroke-width": stroke,
        "stroke-linecap": "round",
        "stroke-dasharray": `${(circ * pct).toFixed(2)} ${circ.toFixed(2)}`,
        transform: `rotate(-90 ${cx} ${cx})`,
      }));
    }
    const num = svgEl("text", {
      class: "tl-ring-num", x: cx, y: cx,
      "text-anchor": "middle", "dominant-baseline": "central",
    });
    num.textContent = score == null ? "?" : String(score);
    svg.appendChild(num);
    return svg;
  }

  /** The score ring plus its label, the headline figure of the badge. */
  function scoreCard(score, label) {
    const card = el("div", "tl-score");
    card.appendChild(scoreRing(score));
    const text = el("div", "tl-score-text");
    text.appendChild(el("div", "tl-score-label", label || "Checked"));
    text.appendChild(el("div", "tl-score-sub",
      score == null ? "Not enough was checked to score" : "Trust score / 100"));
    card.appendChild(text);
    return card;
  }

  /** The badge shell, reused for every state so the node identity is stable.
   *
   * Collapsed by default, per the scope document: "a small color-coded trust
   * badge appears on each post ... Clicking the badge expands a summary panel".
   * It used to render the full 330px panel on every post, which buried the reel
   * you were actually trying to watch behind a wall of text that was usually
   * saying the same thing.
   */
  function makeBadge() {
    const badge = el("div", "tl-badge tl-pending tl-collapsed");
    badge.setAttribute("role", "status");
    badge.setAttribute("aria-live", "polite");

    const row = el("div", "tl-row");
    row.appendChild(el("span", "tl-dot"));
    row.appendChild(el("span", "tl-title", "TrustLens is checking this post…"));
    // Visible even while collapsed: the score, and "Listening… 40%" while the
    // reel's audio is being checked.
    row.appendChild(el("span", "tl-row-status"));
    row.appendChild(el("span", "tl-row-score"));
    // "Scan this reel" — only shown while the badge is idle (see setIdle).
    const scanBtn = el("button", "tl-row-action", "Scan this reel");
    scanBtn.type = "button";
    row.appendChild(scanBtn);
    row.appendChild(el("span", "tl-chevron", "▾"));
    row.appendChild(el("span", "tl-brand", "TrustLens"));

    row.setAttribute("role", "button");
    row.setAttribute("tabindex", "0");
    row.title = "Click for the full breakdown";
    const toggle = () => {
      // Nothing to open while the badge is still a one-line pending message.
      if (badge.childElementCount <= 1) return;
      badge.classList.toggle("tl-collapsed");
    };
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });

    badge.appendChild(row);

    return badge;
  }

  /**
   * Re-class the badge for a new state **without losing layout classes**.
   *
   * Assigning `className` wholesale wiped `tl-floating`, which is what pins the
   * badge to the top-right. Losing it dropped the badge back to `position:
   * relative`, so it flowed to the bottom of the page at full width — the badge
   * appeared, but in the wrong place and cut off. Only the severity class should
   * ever change here.
   */
  function setLevel(badge, level) {
    const floating = badge.classList.contains("tl-floating");
    const collapsed = badge.classList.contains("tl-collapsed");
    badge.className = "tl-badge tl-" + level
      + (floating ? " tl-floating" : "")
      + (collapsed ? " tl-collapsed" : "");
  }

  /** Idle: nothing checked yet. One button, and nothing else on screen. */
  function setIdle(badge, onScan) {
    setLevel(badge, "idle");
    badge.classList.add("tl-collapsed");
    clearBelowRow(badge);
    setRowScore(badge, null);
    setListening(badge, null);
    badge.querySelector(".tl-title").textContent = "Check this reel?";
    const btn = badge.querySelector(".tl-row-action");
    btn.disabled = false;
    // onclick (not addEventListener) so each reel replaces the last handler.
    btn.onclick = (e) => {
      e.stopPropagation();          // don't also toggle the badge open
      btn.disabled = true;
      onScan();
    };
  }

  function setPending(badge, message) {
    setLevel(badge, "pending");
    clearBelowRow(badge);
    badge.querySelector(".tl-title").textContent = message;
    setRowScore(badge, null);
    setListening(badge, null);
  }

  function setRowScore(badge, score) {
    const s = badge.querySelector(".tl-row-score");
    if (s) s.textContent = score == null ? "" : String(score);
  }

  /** "Listening… 40%" in the always-visible row, or clear it with null. */
  function setListening(badge, text) {
    const s = badge.querySelector(".tl-row-status");
    if (s) s.textContent = text || "";
  }

  function fmtCount(n) {
    if (typeof n !== "number") return "?";
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (n >= 1e4) return Math.round(n / 1e3) + "K";
    return n.toLocaleString("en-US");
  }

  /** Live progress line under the title, plus a bar. Reused every tick. */
  function setProgress(badge, percent, stage, elapsed) {
    let wrap = badge.querySelector(".tl-progress");
    if (!wrap) {
      wrap = el("div", "tl-progress");
      wrap.appendChild(el("div", "tl-progress-text"));
      const track = el("div", "tl-progress-track");
      track.appendChild(el("div", "tl-progress-fill"));
      wrap.appendChild(track);
      badge.appendChild(wrap);
    }
    const pct = Math.max(0, Math.min(100, Number(percent) || 0));
    const mins = elapsed >= 60
      ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
      : `${elapsed || 0}s`;
    wrap.querySelector(".tl-progress-text").textContent =
      `${stage || "working"} — ${pct}%  ·  ${mins} elapsed`;
    wrap.querySelector(".tl-progress-fill").style.width = pct + "%";
  }

  function setError(badge, message) {
    setLevel(badge, "error");
    clearBelowRow(badge);
    badge.querySelector(".tl-title").textContent = "TrustLens couldn't check this";
    const detail = el("div", "tl-unchecked", message);
    badge.appendChild(detail);
  }

  function clearBelowRow(badge) {
    const row = badge.querySelector(".tl-row");
    while (badge.lastChild && badge.lastChild !== row) badge.removeChild(badge.lastChild);
  }

  /** Paint a finished verdict. */
  function render(badge, verdict, ctx) {
    const level = verdict.level || "unknown";

    // Serious verdicts open themselves; everything else stays a one-line pill
    // you can click. Hiding a real warning behind a click would defeat the
    // point of the badge, but "caution" and below are exactly the states that
    // were previously covering every reel in text nobody needed to read.
    if (level === "danger" || level === "warning") {
      badge.classList.remove("tl-collapsed");
    } else {
      badge.classList.add("tl-collapsed");
    }

    setLevel(badge, level);
    clearBelowRow(badge);

    const label = LEVEL_LABEL[level] || "Checked";
    const cov1 = verdict.coverage || {};
    badge.querySelector(".tl-title").textContent =
      (level === "unknown" && (cov1.listening || cov1.can_listen) && !cov1.speech_read)
        // Not a failure: the account and caption are done, the audio is next.
        ? (cov1.account_read ? "Account & caption checked, now the audio" : "Caption checked, now the audio")
        : `${label} — ${verdict.headline || ""}`.replace(/\s*—\s*$/, "");

    setRowScore(badge, verdict.score);
    setListening(badge, null);

    // The headline figure: the trust score in its ring. `score` is null when
    // nothing could be checked, and the ring shows "?" rather than a fake number.
    badge.appendChild(scoreCard(verdict.score, verdict.score_label));

    // Where the number comes from: the website's Trust Score engine, one row
    // per module that actually ran, with the weight it got for this post.
    if (Array.isArray(verdict.score_breakdown) && verdict.score_breakdown.length) {
      const box = el("div", "tl-breakdown");
      box.appendChild(el("div", "tl-breakdown-head", "How this score was made"));
      for (const b of verdict.score_breakdown) {
        const row = el("div", "tl-breakdown-row");
        row.appendChild(el("span", "tl-breakdown-name", b.label));
        const bar = el("span", "tl-breakdown-bar");
        const fill = el("span", "tl-breakdown-fill");
        fill.style.width = Math.max(2, Math.min(100, b.score)) + "%";
        fill.className = "tl-breakdown-fill " + (b.score >= 70 ? "is-good" : b.score >= 40 ? "is-mid" : "is-bad");
        bar.appendChild(fill);
        row.appendChild(bar);
        row.appendChild(el("span", "tl-breakdown-num", `${b.score}`));
        row.appendChild(el("span", "tl-breakdown-weight", `×${Math.round(b.weight)}%`));
        box.appendChild(row);
      }
      badge.appendChild(box);
    }

    // Who posted it, and what our fake-account model thinks of that account.
    const post = verdict.post || {};
    const acct = verdict.account || {};
    const cov0 = verdict.coverage || {};
    if (cov0.account_read && typeof acct.prob_fake === "number") {
      const pctFake = Math.round(acct.prob_fake * 100);
      const chip = el("div", "tl-account tl-account-" + (acct.level || "unknown"));
      const head = el("div", "tl-account-head");
      head.appendChild(el("span", "tl-account-name",
        "@" + (acct.username || post.author || "account") + (acct.is_verified ? " ✓" : "")));
      head.appendChild(el("span", "tl-account-pct", pctFake + "% fake-account likelihood"));
      chip.appendChild(head);
      chip.appendChild(el("div", "tl-account-band",
        acct.band === "fake" ? "Profile looks bot-like"
        : acct.band === "uncertain" ? "Ambiguous: not clearly real or fake"
        : "Profile looks like a real account"));
      if (typeof acct.followers === "number") {
        chip.appendChild(el("div", "tl-account-stats",
          `${fmtCount(acct.followers)} followers · ${fmtCount(acct.following)} following · ` +
          `${fmtCount(acct.posts)} posts`));
      }
      if (typeof acct.engagement_rate === "number") {
        chip.appendChild(el("div", "tl-account-stats",
          `Engagement ${acct.engagement_rate}% over recent posts (${acct.engagement_status})`));
      }
      badge.appendChild(chip);
    }
    if (typeof post.likes === "number") {
      const bits = [`${fmtCount(post.likes)} likes`, `${fmtCount(post.comments)} comments`];
      if (post.caption_source === "instagram") bits.push("caption from Instagram");
      badge.appendChild(el("div", "tl-meta", bits.join(" · ")));
    }

    // Reasons
    if (verdict.reasons && verdict.reasons.length) {
      const ul = el("ul", "tl-reasons");
      verdict.reasons.slice(0, 5).forEach((r) => ul.appendChild(el("li", null, r)));
      badge.appendChild(ul);
    }

    // What could not be checked, shown so an unchecked signal is never mistaken
    // for a clean one.
    if (verdict.not_checked && verdict.not_checked.length) {
      badge.appendChild(
        el("div", "tl-unchecked", "Not checked: " + verdict.not_checked.join(" · "))
      );
    }

    // The spoken transcript, once the reel's audio has been read. This is the
    // thing the user explicitly asked to see — "what the video said" — not just
    // the verdict derived from it. textContent-only, like everything else here:
    // the transcript is machine output from a stranger's audio, still untrusted.
    const tr = verdict.transcript;
    if (tr && tr.available && (tr.text || "").trim()) {
      const box = el("div", "tl-transcript");
      if (tr.is_reliable === false) {
        // On music the speech model "hears" words that aren't there (seen:
        // Russian "musical intro" on a Pakistani news reel). Showing that as
        // what the video said would mislead; it isn't scored either.
        box.appendChild(el("div", "tl-transcript-head", "No clear speech (likely music)"));
        box.appendChild(el("div", "tl-transcript-meta",
          `The speech model's unsure guess, ignored: “${tr.text.trim().slice(0, 140)}”`));
      } else {
        box.appendChild(el("div", "tl-transcript-head", "What the video said"));
        box.appendChild(el("div", "tl-transcript-body", tr.text.trim()));
      }

      const bits = [];
      if (tr.language) {
        bits.push("Language: " + String(tr.language).toUpperCase() +
          (typeof tr.confidence === "number"
            ? ` (${Math.round(tr.confidence * 100)}% sure of the language)` : ""));
      }
      if (tr.video_seconds && tr.listened_seconds && tr.video_seconds > tr.listened_seconds + 2) {
        const len = tr.video_seconds >= 120
          ? Math.round(tr.video_seconds / 60) + "-min" : Math.round(tr.video_seconds) + "s";
        bits.push(`Heard the first ${Math.round(tr.listened_seconds)}s of a ${len} video`);
      }
      if (tr.engine) bits.push("Transcribed by " + tr.engine + (tr.via ? " from the " + tr.via : ""));
      if (tr.is_reliable === false) bits.push("unclear audio, so not used for the score");
      if (bits.length) box.appendChild(el("div", "tl-transcript-meta", bits.join(" · ")));
      badge.appendChild(box);
    }

    // Actions
    const actions = el("div", "tl-actions");

    const whyBtn = el("button", "tl-btn", "Why?");
    whyBtn.addEventListener("click", () => onWhy(badge, verdict, whyBtn));
    actions.appendChild(whyBtn);

    // Offer to listen when the audio hasn't been checked yet and there is a
    // video file to listen to.
    const cov = verdict.coverage || {};
    if (ctx && cov.can_listen && !cov.speech_read) {
      const btn = el("button", "tl-btn tl-btn-primary", "▶ Listen to audio");
      btn.title = "Transcribe what is said in this reel, then re-check it. " +
                  "A few seconds for a short reel.";
      btn.addEventListener("click", () => ctx.onTranscribe(btn));
      actions.appendChild(btn);
    }

    badge.appendChild(actions);
    return badge;
  }

  /** The "Why?" button: ask the gateway for a plain-English explanation. */
  async function onWhy(badge, verdict, btn) {
    const existing = badge.querySelector(".tl-explain");
    if (existing) {                       // toggle off
      existing.remove();
      btn.textContent = "Why?";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Thinking…";
    try {
      const res = await TL.api.explain(verdict);
      const box = el("div", "tl-explain", res.text || "No explanation available.");
      const src = el("span", "tl-source",
        res.source === "gemini"
          ? "Explained by Gemini, from the evidence above."
          : "Explained from the detected patterns (Gemini key not configured).");
      box.appendChild(src);
      badge.appendChild(box);
      btn.textContent = "Hide";
    } catch (err) {
      const box = el("div", "tl-explain", `Couldn't get an explanation: ${err.message}`);
      badge.appendChild(box);
      btn.textContent = "Why?";
    } finally {
      btn.disabled = false;
    }
  }

  return { makeBadge, setIdle, setPending, setError, setProgress, setListening, render };
})();

/* ---------------------------------------------------------------------- *
 * Analysis driver, one post at a time.
 * ---------------------------------------------------------------------- */
TL.listening = new Set();   // reels whose audio is being listened to right now

/** "Scan this reel" mode: you've stayed on this reel for a moment, so fetch
 *  its data now (network only) and pressing Scan answers almost at once. */
TL.warmed = new Set();
TL.warmPost = function (postData) {
  if (TL.warmed.has(postData.key) || TL.cache.has(postData.key)) return;
  TL.warmed.add(postData.key);
  TL.api.warm({
    page_url: postData.page_url,
    username: postData.author || (TL.pageMedia.get(postData.key) || {}).username || "",
    media: TL.pageMedia.get(postData.key) || undefined,
  });
};

/* ---------------------------------------------------------------------- *
 * Reel data from Instagram's own page (see page_hook.js).
 * Instagram loads the next reels before you reach them; we hand those to
 * the gateway so each one is already checked when you swipe to it.
 * ---------------------------------------------------------------------- */
TL.pageMedia = new Map();   // shortcode -> reel data as the page loaded it
TL.pageOrder = [];          // shortcodes in the order Instagram listed them
// Two kinds of pre-check, kept apart on purpose:
//  - data: remember the next reels and fetch their poster's profile. Network
//    only, no CPU, so it happens straight away.
//  - audio: listen to the next reels. Uses the CPU, so it only starts once the
//    reel on screen is finished — measured: doing both at once slowed the
//    on-screen reel down and the pre-checks were thrown away anyway.
TL.prefetchedData = new Set();
TL.prefetchedAudio = new Set();
const prefetchTimers = {};

window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || e.data.__trustlens !== "media") return;
  if (!Array.isArray(e.data.items)) return;
  for (const it of e.data.items.slice(0, 60)) {
    if (!it || typeof it.code !== "string") continue;
    const prev = TL.pageMedia.get(it.code) || {};
    const merged = { ...prev };
    for (const k in it) if (it[k] || merged[k] === undefined) merged[k] = it[k];
    TL.pageMedia.set(it.code, merged);
    if (!TL.pageOrder.includes(it.code)) TL.pageOrder.push(it.code);
  }
  TL.schedulePrefetch({ listen: false });
  if (TL.currentIsFinished()) TL.schedulePrefetch({ listen: true });
});

/** Is the reel on screen fully checked (so the CPU is free for the next ones)? */
TL.currentIsFinished = function () {
  const cur = TL.observer && TL.observer.currentKey();
  const done = cur && TL.cache.get(cur);
  if (!done || done.status !== "done") return false;
  const cov = done.verdict.coverage || {};
  return cov.speech_read || !(cov.can_listen || cov.listening);
};

TL.schedulePrefetch = function ({ listen }) {
  // Pre-checking the NEXT reels only makes sense when every reel is checked
  // automatically. In "Scan this reel" mode nothing is done for a reel you
  // didn't ask about.
  if (!TL.settings.autoScan) return;
  const kind = listen ? "audio" : "data";
  if (prefetchTimers[kind]) clearTimeout(prefetchTimers[kind]);
  prefetchTimers[kind] = setTimeout(() => {
    prefetchTimers[kind] = null;
    if (!TL.settings.enabled) return;
    if (listen && TL.settings.autoTranscribe === false) return;
    const done = listen ? TL.prefetchedAudio : TL.prefetchedData;
    const cur = TL.observer && TL.observer.currentKey();
    const at = TL.pageOrder.indexOf(cur);
    const upcoming = (at >= 0 ? TL.pageOrder.slice(at + 1) : TL.pageOrder)
      .filter((c) => c !== cur && !done.has(c))
      .slice(0, listen ? 2 : 4)
      .map((c) => TL.pageMedia.get(c))
      .filter(Boolean);
    if (!upcoming.length) return;
    upcoming.forEach((m) => done.add(m.code));
    TL.api.prefetch(upcoming, { listen });
  }, listen ? 200 : 400);
};

TL.analyzePost = async function (postData, badge, { transcribe = false } = {}) {
  const key = postData.key;
  // One badge describes whatever is on screen. If you swiped on while this was
  // running, the answer belongs to a reel you are no longer looking at and must
  // not be painted over the current one.
  const isCurrent = () => badge.isConnected && badge.dataset.tlKey === key;

  if (!transcribe) TL.schedulePrefetch({ listen: false });   // you moved: line up the next reels

  const cached = TL.cache.get(key);
  if (cached && cached.status === "done" &&
      (!transcribe || (cached.verdict.coverage || {}).speech_read)) {
    if (isCurrent()) {
      TL.ui.render(badge, cached.verdict, makeCtx(postData, badge));
      maybeAutoListen(cached.verdict);
      if (TL.currentIsFinished()) TL.schedulePrefetch({ listen: true });
    }
    return cached.verdict;
  }

  if (transcribe) {
    if (TL.listening.has(key)) return null;
    TL.listening.add(key);
    TL.ui.setListening(badge, "Listening…");
  } else {
    TL.ui.setPending(badge, postData.is_reel
      ? "Fetching this reel from Instagram…"
      : "TrustLens is checking this post…");
  }

  // Poll the gateway for what it is doing right now, so the badge always shows
  // a live step ("Checking @name's account…", "Listening… 40%") rather than a
  // spinner that looks like a hang.
  const tick = async () => {
    const p = await TL.api.progress(postData.page_url);
    if (!isCurrent() || !p || p.state === "idle") return;
    if (transcribe) {
      TL.ui.setListening(badge, typeof p.percent === "number"
        ? `Listening… ${p.percent}%` : "Listening…");
    } else if (p.stage && badge.classList.contains("tl-pending")) {
      badge.querySelector(".tl-title").textContent = p.stage;
    }
  };
  const ticker = setInterval(tick, 600);

  // Profile stats read off an open profile page (free). Anywhere else the
  // gateway fetches the poster's profile itself.
  const account = TL.ig.readProfile(postData.author);

  try {
    const verdict = await TL.api.analyze(
      {
        page_url: postData.page_url,
        caption: postData.caption,
        on_screen_text: postData.on_screen_text,
        is_reel: postData.is_reel,
        username: postData.author || (TL.pageMedia.get(key) || {}).username || "",
        account: account || undefined,
        media: TL.pageMedia.get(key) || undefined,
        // Start listening to the reel's audio on the server straight away,
        // instead of after this answer comes back.
        listen: !transcribe && TL.settings.autoTranscribe !== false,
      },
      { transcribe }
    );

    TL.cache.set(key, { status: "done", verdict });
    if (isCurrent()) {
      TL.ui.render(badge, verdict, makeCtx(postData, badge));
      maybeAutoListen(verdict);
      // This reel is done: use the free CPU to get the next ones ready.
      if (TL.currentIsFinished()) TL.schedulePrefetch({ listen: true });
    }
    return verdict;
  } catch (err) {
    TL.log("analysis failed", err);
    if (isCurrent()) {
      if (transcribe && cached && cached.verdict) {
        // Keep the verdict we already had; just say the listening failed.
        TL.ui.render(badge, cached.verdict, makeCtx(postData, badge));
        TL.ui.setListening(badge, "Couldn't listen");
      } else {
        TL.ui.setError(badge, err.message);
      }
    }
    return null;
  } finally {
    clearInterval(ticker);
    if (transcribe) TL.listening.delete(key);
  }

  function maybeAutoListen(v) {
    if (transcribe || !TL.settings.autoTranscribe) return;
    const cov = v.coverage || {};
    if (cov.speech_read || !(cov.listening || cov.can_listen)) return;
    // The server is usually already listening (started by the first request);
    // this just waits for that job and paints the final verdict.
    if (isCurrent()) TL.analyzePost(postData, badge, { transcribe: true });
  }
};

function makeCtx(postData, badge) {
  return {
    isReel: postData.is_reel,
    onTranscribe: (btn) => {
      btn.disabled = true;
      btn.textContent = "Listening…";
      TL.analyzePost(postData, badge, { transcribe: true });
    },
  };
}

/* ---------------------------------------------------------------------- *
 * Boot
 * ---------------------------------------------------------------------- */
(async function boot() {
  await TL.loadSettings();
  TL.log("loaded on", location.href, TL.settings);

  // Let the popup trigger a scan of whatever is on screen right now.
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.type === "TL_SCAN_NOW") {
      TL.observer.scanNow({ force: true });
      sendResponse({ ok: true });
    }
    if (msg && msg.type === "TL_SETTINGS") {
      TL.settings = { ...TL.settings, ...msg.settings };
      sendResponse({ ok: true });
    }
    return true;
  });

  TL.observer.start();
})();
