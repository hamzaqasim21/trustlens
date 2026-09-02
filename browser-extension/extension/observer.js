/*
 * observer.js: decides which post you are looking at and badges it.
 *
 * Rule: don't insert anything into Instagram's own DOM.
 *
 * Instagram is a React app. Putting a badge inside an <article>, or as a sibling
 * next to one, makes the live DOM disagree with what React rendered. React then
 * throws hydration error #418 repeatedly and tears down its component tree. That
 * is what left the reel page blank with a console full of errors, and it took a
 * few rounds to trace back to us rather than to Instagram.
 *
 * So the badge lives in its own layer attached to <html>, which React neither
 * created nor manages. One badge, pinned top-right, describing whichever post is
 * currently in view on the feed or in a reel. A single badge makes the earlier
 * flood impossible, and staying outside Instagram's tree means there is no React
 * state left to corrupt.
 */
window.TL = window.TL || {};

TL.observer = (function () {
  "use strict";

  let mutationObserver = null;
  let scanTimer = null;
  let rafPending = false;
  let lastUrl = location.href;

  let badge = null;        // the one badge element (lives under <html>)
  let shownKey = null;     // postKey the badge currently describes
  let analyzeTimer = null;
  let heartbeat = null;

  const DEBOUNCE_MS = 250;
  const SETTLE_MS = 300;   // wait this long after scrolling stops before analysing

  // --------------------------------------------------------------------- //
  // The badge element — created lazily, kept out of Instagram's DOM.
  // --------------------------------------------------------------------- //
  function ensureBadge() {
    if (badge && badge.isConnected) return badge;
    badge = TL.ui.makeBadge();
    badge.classList.add("tl-floating");
    // <html>, not <body>: Instagram rewrites the body subtree on navigation and
    // would drop a body-level node. React does not manage documentElement's
    // direct children, so nothing here can disturb its tree.
    (document.documentElement || document.body).appendChild(badge);
    return badge;
  }

  function removeBadge() {
    if (badge) badge.remove();
    badge = null;
    shownKey = null;
  }

  // --------------------------------------------------------------------- //
  // Which post am I looking at?
  // --------------------------------------------------------------------- //

  /** The feed article whose centre is nearest the middle of the viewport. */
  function articleInView() {
    const mid = window.innerHeight / 2;
    let best = null;
    let bestDist = Infinity;
    for (const a of document.querySelectorAll("article")) {
      const r = a.getBoundingClientRect();
      if (r.height < 80) continue;                       // not a real post card
      if (r.bottom < 80 || r.top > window.innerHeight - 40) continue;  // off-screen
      const dist = Math.abs((r.top + r.bottom) / 2 - mid);
      if (dist < bestDist) { bestDist = dist; best = a; }
    }
    return best;
  }

  /** The post the badge should currently describe, or null if none. */
  function currentPost() {
    const type = TL.ig.pageType();

    // Reel / post detail (incl. the /reels/ swipe feed): one item, from the URL.
    if (type === "reel" || type === "post") {
      const data = TL.ig.readPost(null);
      return data.key ? data : null;
    }

    // Feed / profile: the article nearest the viewport centre.
    if (type === "feed" || type === "profile" || type === "other") {
      const article = articleInView();
      if (!article) return null;
      const data = TL.ig.readPost(article);
      return data.key ? data : null;
    }

    return null;
  }

  // --------------------------------------------------------------------- //
  // Update the badge to match what is in view.
  // --------------------------------------------------------------------- //
  function update({ immediate = false } = {}) {
    if (!TL.settings.enabled) { removeBadge(); return; }

    const type = (() => { try { return TL.ig.pageType(); } catch (e) { return "?"; } })();

    let data = null;
    try {
      data = currentPost();
    } catch (e) {
      // Never fail silently. A badge that says what went wrong is debuggable
      // from a screenshot; a missing badge tells nobody anything, which is
      // exactly why the reel page took several rounds to diagnose.
      TL.log("currentPost failed", e);
      TL.ui.setError(ensureBadge(), "Couldn't read this page (" + type + "): " + e.message);
      shownKey = null;
      return;
    }

    if (!data || !data.key) {
      // On a post/reel URL this means the page had not rendered yet, say so and
      // let the next tick pick it up, rather than leaving a blank screen.
      if (type === "reel" || type === "post") {
        TL.ui.setPending(ensureBadge(), "Looking for this " + type + "…");
      }
      shownKey = null;
      return;
    }

    // A reel/post page is always worth badging even with thin text — "not
    // checked" is an honest state. Only the feed skips empty cards, so scrolling
    // past the stories tray does not flicker the badge.
    const thin = !data.caption && !data.on_screen_text && !data.is_reel;
    if (thin && type !== "reel" && type !== "post") return;

    // Already showing this exact post, nothing to do. (Scrolling fires this
    // constantly; this keeps it cheap and stops needless re-analysis.)
    if (shownKey === data.key && badge && badge.isConnected) return;

    shownKey = data.key;
    const el = ensureBadge();
    if (!TL.settings.autoScan) return;

    // Analyse the post you SETTLE on, not every one that flies past mid-scroll.
    // otherwise the badge flickers through a dozen verdicts and fires a gateway
    // call for each. `immediate` is for the popup's "check now" button.
    if (analyzeTimer) { clearTimeout(analyzeTimer); analyzeTimer = null; }
    const runAnalyze = () => {
      if (shownKey === data.key) TL.analyzePost(data, el, { transcribe: false });
    };
    if (immediate) runAnalyze();
    else { TL.ui.setPending(el, "TrustLens is checking this post…"); analyzeTimer = setTimeout(runAnalyze, SETTLE_MS); }
  }

  // Coalesce the flood of scroll/mutation events into one update per frame.
  function scheduleUpdate() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => { rafPending = false; update(); });
  }

  function scheduleScan() {
    if (scanTimer) clearTimeout(scanTimer);
    scanTimer = setTimeout(() => {
      scanTimer = null;
      checkUrlChange();
      update();
    }, DEBOUNCE_MS);
  }

  /** Instagram changes the URL without a navigation event; note it and re-check. */
  function checkUrlChange() {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    // A new page, let the badge re-point at whatever is there now.
    shownKey = null;
    TL.log("navigated to", location.href);
  }

  // Exposed for the popup's "Check what's on screen now" button.
  function scanNow({ force = false } = {}) {
    if (!TL.settings.enabled && !force) return;
    shownKey = null;                    // force a fresh look
    update({ immediate: true });
  }

  function start() {
    mutationObserver = new MutationObserver(scheduleScan);
    mutationObserver.observe(document.body, { childList: true, subtree: true });

    // The badge follows the post you scroll to. Capture-phase catches scrolling
    // inside any nested scroller, not just the window.
    window.addEventListener("scroll", scheduleUpdate, { passive: true, capture: true });
    window.addEventListener("resize", scheduleUpdate, { passive: true });

    // pushState/replaceState do not emit events; popstate covers only Back.
    window.addEventListener("popstate", scheduleScan);
    for (const method of ["pushState", "replaceState"]) {
      const original = history[method];
      history[method] = function () {
        const result = original.apply(this, arguments);
        scheduleScan();
        return result;
      };
    }

    // Safety net. A reel opened by a fresh page load renders after the content
    // script runs, and Instagram does not always emit a mutation we catch at the
    // right moment, leaving a blank page with no badge and no explanation. This
    // cheap re-check (one call, no network unless the post actually changed)
    // guarantees the badge turns up within a couple of seconds regardless.
    heartbeat = setInterval(() => {
      if (!badge || !badge.isConnected || shownKey === null) update();
    }, 2000);

    update();
    TL.log("observer started on", TL.ig.pageType(), location.href);
  }

  function stop() {
    if (mutationObserver) mutationObserver.disconnect();
    mutationObserver = null;
    if (heartbeat) { clearInterval(heartbeat); heartbeat = null; }
    window.removeEventListener("scroll", scheduleUpdate, { capture: true });
    window.removeEventListener("resize", scheduleUpdate);
    removeBadge();
  }

  return { start, stop, scanNow };
})();
