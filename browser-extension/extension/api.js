/*
 * api.js: talks to the TrustLens gateway. The only network code in the
 * extension, and it only ever calls 127.0.0.1:8100.
 *
 * Nothing is sent anywhere else: no analytics, no third-party host. The Gemini
 * call happens on the gateway, so no API key is ever present in this codebase.
 */
window.TL = window.TL || {};

TL.api = (function () {
  "use strict";

  async function post(path, body, timeoutMs = 120000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(TL.GATEWAY + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const j = await res.json();
          if (j && j.detail) detail = j.detail;
        } catch (e) { /* keep the status line */ }
        throw new Error(detail);
      }
      return await res.json();
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("The gateway took too long to answer.");
      }
      // A refused connection is the common case (gateway not started) and
      // deserves an instruction, not a stack trace.
      if (err instanceof TypeError) {
        throw new Error(
          "Can't reach TrustLens. Start the gateway:  uvicorn main:app --port 8100"
        );
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Analyse one post.
   * `transcribe` is opt-in per call because Whisper on a CPU runs at about
   * realtime, a 60-second reel is a 60-second wait, which must never happen
   * unasked while someone is scrolling.
   */
  async function analyze(payload, { transcribe = false } = {}) {
    const timeout = transcribe ? 900000 : 90000;
    return post("/analyze", { ...payload, transcribe }, timeout);
  }

  async function explain(verdict) {
    return post("/explain", { verdict }, 60000);
  }

  /** How far a running transcription has got. Never throws, the caller is a
   *  progress ticker and a hiccup there must not disturb the analysis. */
  async function progress(pageUrl) {
    try {
      const res = await fetch(
        `${TL.GATEWAY}/progress?page_url=${encodeURIComponent(pageUrl)}`,
        { cache: "no-store" }
      );
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  async function health() {
    const res = await fetch(TL.GATEWAY + "/health");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  return { analyze, explain, health, progress };
})();
