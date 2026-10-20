/*
 * background.js: MV3 service worker.
 *
 * Two jobs:
 *
 * 1. Every call to the gateway goes through here. A content script's fetch()
 *    runs as instagram.com, and newer Chromium browsers (Chrome, Opera, Edge)
 *    block or prompt when a public website reaches into 127.0.0.1 ("Local
 *    Network Access"). The extension's own worker has host permission for the
 *    gateway, so its requests are not subject to that — relaying through here
 *    is the pattern Chrome recommends for exactly this case.
 * 2. A dot on the toolbar icon showing whether the backend is up.
 *
 * A service worker is stopped and restarted by the browser at will, so it keeps
 * no state in memory; every handler reads what it needs from storage.
 */

const GATEWAY = "http://127.0.0.1:8100";
// 3: "Scan this reel" (on demand) became the default instead of checking
// every reel automatically.
const SETTINGS_VERSION = 3;

chrome.runtime.onInstalled.addListener(async () => {
  const { settings } = await chrome.storage.local.get("settings");
  if (!settings || settings.version !== SETTINGS_VERSION) {
    await chrome.storage.local.set({
      settings: {
        enabled: settings ? settings.enabled !== false : true,
        autoScan: false,
        autoTranscribe: true,
        version: SETTINGS_VERSION,
      },
    });
  }
  updateActionBadge();
});

chrome.runtime.onStartup.addListener(updateActionBadge);

async function callGateway({ path, method = "GET", body, timeoutMs = 90000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(GATEWAY + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
    if (!res.ok) {
      const detail = data && data.detail
        ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
        : `HTTP ${res.status}`;
      return { ok: false, status: res.status, error: detail };
    }
    return { ok: true, status: res.status, data };
  } catch (err) {
    if (err.name === "AbortError") {
      return { ok: false, status: 0, error: "The gateway took too long to answer." };
    }
    return {
      ok: false, status: 0, unreachable: true,
      error: "Can't reach TrustLens. Start the services with start_all.ps1.",
    };
  } finally {
    clearTimeout(timer);
  }
}

/** A dot on the toolbar icon showing whether the backend is up. */
async function updateActionBadge() {
  const r = await callGateway({ path: "/health", timeoutMs: 5000 });
  if (!r.ok) {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
    return;
  }
  const modules = (r.data && r.data.modules) || {};
  const down = Object.values(modules).filter((m) => !m.up).length;
  if (down === 0) {
    chrome.action.setBadgeText({ text: "" });
  } else {
    chrome.action.setBadgeText({ text: String(down) });
    chrome.action.setBadgeBackgroundColor({ color: "#ea580c" });
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "TL_API") {
    callGateway(msg.request || {}).then(sendResponse);
    return true; // keep the channel open for the async reply
  }
  if (msg && msg.type === "TL_REFRESH_STATUS") {
    updateActionBadge().then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
