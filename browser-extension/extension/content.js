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

  /** The badge shell, reused for every state so the node identity is stable. */
  function makeBadge() {
    const badge = el("div", "tl-badge tl-pending");
    badge.setAttribute("role", "status");
    badge.setAttribute("aria-live", "polite");

    const row = el("div", "tl-row");
    row.appendChild(el("span", "tl-dot"));
    row.appendChild(el("span", "tl-title", "TrustLens is checking this post…"));
    row.appendChild(el("span", "tl-brand", "TrustLens"));
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
    badge.className = "tl-badge tl-" + level + (floating ? " tl-floating" : "");
  }

  function setPending(badge, message) {
    setLevel(badge, "pending");
    clearBelowRow(badge);
    badge.querySelector(".tl-title").textContent = message;
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
    setLevel(badge, level);
    clearBelowRow(badge);

    const label = LEVEL_LABEL[level] || "Checked";
    badge.querySelector(".tl-title").textContent =
      `${label} — ${verdict.headline || ""}`.replace(/\s*—\s*$/, "");

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
      box.appendChild(el("div", "tl-transcript-head", "What the video said"));
      box.appendChild(el("div", "tl-transcript-body", tr.text.trim()));

      const bits = [];
      if (tr.language) bits.push("Language: " + String(tr.language).toUpperCase());
      if (typeof tr.confidence === "number") {
        bits.push("Confidence: " + Math.round(tr.confidence * 100) + "%");
      }
      if (tr.is_reliable === false) bits.push("low confidence — read as rough");
      if (bits.length) box.appendChild(el("div", "tl-transcript-meta", bits.join(" · ")));
      badge.appendChild(box);
    }

    // Actions
    const actions = el("div", "tl-actions");

    const whyBtn = el("button", "tl-btn", "Why?");
    whyBtn.addEventListener("click", () => onWhy(badge, verdict, whyBtn));
    actions.appendChild(whyBtn);

    // Offer transcription when the post is a reel whose audio was not read yet.
    const cov = verdict.coverage || {};
    const speechRead = cov.speech_read || (verdict.text_sources || []).includes("speech");
    if (ctx && ctx.isReel && !speechRead) {
      const btn = el("button", "tl-btn tl-btn-primary", "▶ Listen to audio");
      btn.title = "Download the reel and transcribe what is said, then re-check. " +
                  "On this machine that takes a few minutes for a one-minute reel.";
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

  return { makeBadge, setPending, setError, setProgress, render };
})();

/* ---------------------------------------------------------------------- *
 * Analysis driver, one post at a time.
 * ---------------------------------------------------------------------- */
TL.analyzePost = async function (postData, badge, { transcribe = false } = {}) {
  const cacheKey = postData.key + (transcribe ? ":speech" : "");

  // Re-rendering is constant on Instagram; never redo work already done.
  const cached = TL.cache.get(cacheKey);
  if (cached && cached.status === "done") {
    TL.ui.render(badge, cached.verdict, makeCtx(postData, badge));
    return cached.verdict;
  }

  TL.ui.setPending(
    badge,
    transcribe ? "Listening to the video…" : "TrustLens is checking this post…"
  );

  // While /analyze is blocked on Whisper, poll the gateway so the badge can show
  // real progress. Without this a multi-minute wait looks identical to a hang.
  let ticker = null;
  if (transcribe) {
    const t0 = Date.now();
    const tick = async () => {
      const p = await TL.api.progress(postData.page_url);
      if (!p || p.state === "idle") {
        TL.ui.setProgress(badge, 0, "Starting…",
                          Math.round((Date.now() - t0) / 1000));
        return;
      }
      if (p.state === "failed") {
        TL.ui.setProgress(badge, 0, p.stage || "Failed",
                          p.elapsed ?? Math.round((Date.now() - t0) / 1000));
        return;
      }
      TL.ui.setProgress(badge, p.percent, p.stage,
                        p.elapsed ?? Math.round((Date.now() - t0) / 1000));
    };
    tick();
    ticker = setInterval(tick, 1500);
  }

  // Profile stats are only visible on a profile page. Anywhere else we send
  // nothing rather than zeros, and the gateway reports the account as unchecked.
  const account = TL.ig.readProfile(postData.author);

  try {
    const verdict = await TL.api.analyze(
      {
        page_url: postData.page_url,
        caption: postData.caption,
        on_screen_text: postData.on_screen_text,
        is_reel: postData.is_reel,
        account: account || undefined,
      },
      { transcribe }
    );

    TL.cache.set(cacheKey, { status: "done", verdict });
    TL.ui.render(badge, verdict, makeCtx(postData, badge));
    return verdict;
  } catch (err) {
    TL.cache.set(cacheKey, { status: "error", error: err.message });
    TL.ui.setError(badge, err.message);
    TL.log("analysis failed", err);
    return null;
  } finally {
    if (ticker) clearInterval(ticker);
  }
};

function makeCtx(postData, badge) {
  return {
    isReel: postData.is_reel,
    onTranscribe: (btn) => {
      btn.disabled = true;
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
