/*
 * api.js: talks to the TrustLens gateway, and only to the gateway.
 *
 * Requests are relayed through the extension's background worker (see
 * background.js for why). Nothing is sent anywhere else: no analytics, no
 * third-party host, and no API key ever exists in the extension's code.
 */
window.TL = window.TL || {};

TL.api = (function () {
  "use strict";

  function relay(request) {
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage({ type: "TL_API", request }, (reply) => {
          const lastError = chrome.runtime.lastError;
          if (lastError || !reply) {
            reject(new Error(
              "TrustLens was updated or restarted. Refresh this Instagram tab (F5)."
            ));
            return;
          }
          if (!reply.ok) {
            const err = new Error(reply.error || "Request failed");
            err.status = reply.status;
            reject(err);
            return;
          }
          resolve(reply.data);
        });
      } catch (e) {
        // "Extension context invalidated": the extension was reloaded while
        // this tab kept running the old copy of this script.
        reject(new Error("TrustLens was updated. Refresh this Instagram tab (F5)."));
      }
    });
  }

  /**
   * Analyse one post. `transcribe` asks the gateway to listen to a reel's
   * audio (a few seconds on this machine for a short reel).
   */
  async function analyze(payload, { transcribe = false } = {}) {
    return relay({
      path: "/analyze",
      method: "POST",
      body: { ...payload, transcribe },
      timeoutMs: transcribe ? 300000 : 90000,
    });
  }

  /** Hand the next reels to the gateway so it can check them in advance. */
  async function prefetch(items, { listen = true } = {}) {
    try {
      return await relay({ path: "/prefetch", method: "POST", body: { items, listen }, timeoutMs: 10000 });
    } catch (e) {
      return null;   // a missed pre-check only costs speed, never correctness
    }
  }

  /** Get a reel ready to scan (fetch its data only; nothing is analysed). */
  async function warm(payload) {
    try {
      return await relay({ path: "/warm", method: "POST", body: payload, timeoutMs: 8000 });
    } catch (e) {
      return null;   // only costs speed
    }
  }

  async function explain(verdict) {
    return relay({ path: "/explain", method: "POST", body: { verdict }, timeoutMs: 60000 });
  }

  /** How far a running transcription has got. Never throws. */
  async function progress(pageUrl) {
    try {
      return await relay({
        path: `/progress?page_url=${encodeURIComponent(pageUrl)}`,
        timeoutMs: 5000,
      });
    } catch (e) {
      return null;
    }
  }

  async function health() {
    return relay({ path: "/health", timeoutMs: 5000 });
  }

  return { analyze, explain, health, progress, prefetch, warm };
})();
