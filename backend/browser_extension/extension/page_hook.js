/*
 * page_hook.js: runs inside Instagram's own page (the "MAIN" world), not in the
 * extension's isolated world.
 *
 * Why: Instagram's page downloads the data for the reels you are about to see
 * before you swipe to them — caption, poster, video address. That is the same
 * data RapidAPI returns (RapidAPI reads the same Instagram API). Reading it as
 * the page receives it means the gateway doesn't have to wait ~4-7s for
 * RapidAPI for the reel on screen, and can check the NEXT reels in the
 * background so their verdict is ready the moment you swipe.
 *
 * What it does and doesn't do:
 * - It only reads responses Instagram's own code already requested. It sends
 *   no requests of its own, changes nothing, and never touches cookies.
 * - It passes along a handful of public fields per reel (see pick()) to the
 *   extension's content script with window.postMessage. The gateway treats
 *   them as untrusted and re-validates everything.
 * - If Instagram changes its data format, this finds nothing and the extension
 *   falls back to RapidAPI exactly as before. It can't make a verdict wrong.
 */
(function () {
  "use strict";
  if (window.__trustlensHook) return;
  window.__trustlensHook = true;

  const CODE = /^[A-Za-z0-9_-]{5,40}$/;
  const sent = new Set();

  function isMedia(o) {
    return o && typeof o.code === "string" && CODE.test(o.code) &&
      o.user && typeof o.user.username === "string";
  }

  function captionOf(o) {
    if (o.caption && typeof o.caption.text === "string") return o.caption.text;
    const edges = o.edge_media_to_caption && o.edge_media_to_caption.edges;
    if (edges && edges[0] && edges[0].node) return edges[0].node.text || "";
    return "";
  }

  function videoOf(o) {
    let vv = o.video_versions;
    if (!vv && Array.isArray(o.carousel_media)) {
      const slide = o.carousel_media.find((s) => s && s.video_versions);
      vv = slide && slide.video_versions;
    }
    if (Array.isArray(vv) && vv[0] && typeof vv[0].url === "string") return vv[0].url;
    return typeof o.video_url === "string" ? o.video_url : "";
  }

  // Instagram's player streams a reel as separate video and audio tracks, and
  // describes them in `video_dash_manifest` (an MPEG-DASH XML document). The
  // audio-only track is ~0.5 MB a minute against 7-19 MB for the video, so on
  // a slow connection it's the difference between listening in a second or a
  // minute. Lowest bitrate is plenty for speech. Empty if there's no manifest
  // — the gateway then falls back to the video file.
  function audioOf(o) {
    const mpd = o.video_dash_manifest;
    if (typeof mpd !== "string" || mpd.indexOf("audio") === -1) return "";
    try {
      const doc = new DOMParser().parseFromString(mpd, "application/xml");
      let best = null;
      for (const rep of doc.getElementsByTagName("Representation")) {
        const set = rep.parentElement;
        const kind = (rep.getAttribute("mimeType") || "") + " " +
          ((set && (set.getAttribute("mimeType") || set.getAttribute("contentType"))) || "");
        if (kind.indexOf("audio") === -1) continue;
        const base = rep.getElementsByTagName("BaseURL")[0];
        if (!base || !base.textContent) continue;
        const bw = Number(rep.getAttribute("bandwidth")) || Infinity;
        if (!best || bw < best.bw) best = { url: base.textContent.trim(), bw };
      }
      return best ? best.url : "";
    } catch (e) {
      return "";
    }
  }

  function pick(o) {
    const video = videoOf(o);
    return {
      code: o.code,
      caption: String(captionOf(o) || "").slice(0, 5000),
      username: o.user.username,
      full_name: String(o.user.full_name || "").slice(0, 100),
      is_verified: !!o.user.is_verified,
      is_private: !!o.user.is_private,
      is_video: !!video,
      has_audio: video ? o.has_audio !== false : false,
      video_url: video,
      audio_url: video ? audioOf(o) : "",
      like_count: Number(o.like_count) || 0,
      comment_count: Number(o.comment_count) || 0,
    };
  }

  function walk(node, out, depth) {
    if (!node || typeof node !== "object" || depth > 80 || out.length > 60) return;
    if (Array.isArray(node)) {
      for (const x of node) walk(x, out, depth + 1);
      return;
    }
    if (isMedia(node)) {
      out.push(pick(node));
      // A carousel's slides are part of the same post; don't descend into them.
      return;
    }
    for (const k in node) {
      const v = node[k];
      if (v && typeof v === "object") walk(v, out, depth + 1);
    }
  }

  function emit(items) {
    const fresh = [];
    for (const it of items) {
      const key = it.code + "|" + (it.video_url ? 1 : 0) + "|" + (it.caption ? 1 : 0);
      if (sent.has(key)) continue;
      sent.add(key);
      fresh.push(it);
    }
    if (fresh.length) {
      window.postMessage({ __trustlens: "media", items: fresh }, location.origin);
    }
  }

  function scanText(text) {
    if (typeof text !== "string" || text.length < 20) return;
    // Cheap pre-check before parsing anything big.
    if (text.indexOf('"code"') === -1 || text.indexOf('"username"') === -1) return;
    const out = [];
    const body = text.replace(/^for \(;;\);/, "");
    try {
      walk(JSON.parse(body), out, 0);
    } catch (e) {
      // Some endpoints stream several JSON documents, one per line.
      for (const line of body.split("\n")) {
        const t = line.trim();
        if (!t || (t[0] !== "{" && t[0] !== "[")) continue;
        try { walk(JSON.parse(t), out, 0); } catch (e2) { /* not JSON */ }
      }
    }
    if (out.length) emit(out);
  }

  const INTERESTING = /graphql|\/api\/v1\/|\/api\/graphql/;

  // ---- fetch() ----
  const origFetch = window.fetch;
  window.fetch = function () {
    const p = origFetch.apply(this, arguments);
    try {
      const a = arguments[0];
      const url = String((a && a.url) || a || "");
      if (INTERESTING.test(url)) {
        p.then((res) => {
          try { res.clone().text().then(scanText, () => {}); } catch (e) { /* ignore */ }
        }, () => {});
      }
    } catch (e) { /* never break Instagram */ }
    return p;
  };

  // ---- XMLHttpRequest ----
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    try { this.__tlUrl = String(url || ""); } catch (e) { /* ignore */ }
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    try {
      if (INTERESTING.test(this.__tlUrl || "")) {
        this.addEventListener("load", () => {
          try {
            if (this.responseType === "" || this.responseType === "text") scanText(this.responseText);
          } catch (e) { /* ignore */ }
        });
      }
    } catch (e) { /* ignore */ }
    return origSend.apply(this, arguments);
  };

  // ---- data embedded in the page on first load ----
  function scanEmbedded() {
    for (const s of document.querySelectorAll('script[type="application/json"]')) {
      if (s.__tlScanned) continue;
      s.__tlScanned = true;
      const t = s.textContent || "";
      if (t.indexOf('"video_versions"') !== -1 || t.indexOf('"caption"') !== -1) scanText(t);
    }
  }
  document.addEventListener("DOMContentLoaded", scanEmbedded);
  window.addEventListener("load", scanEmbedded);
})();
