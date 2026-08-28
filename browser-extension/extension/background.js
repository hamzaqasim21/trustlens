/*
 * background.js: MV3 service worker.
 *
 * Deliberately minimal. All the analysis happens in the content script (which
 * can see the page) and the gateway (which holds the models and the key), so
 * this only sets first-run defaults and reports gateway reachability to the
 * popup's badge.
 *
 * A service worker is stopped and restarted by Chrome at will, so it keeps no
 * state in memory, every handler reads what it needs from storage.
 */

const GATEWAY = "http://127.0.0.1:8100";

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get("settings");
  if (!existing || !existing.settings) {
    await chrome.storage.local.set({
      settings: { enabled: true, autoScan: true, autoTranscribe: false },
    });
  }
  updateActionBadge();
});

chrome.runtime.onStartup.addListener(updateActionBadge);

/** A dot on the toolbar icon showing whether the backend is up. */
async function updateActionBadge() {
  try {
    const res = await fetch(`${GATEWAY}/health`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    const modules = data.modules || {};
    const down = Object.values(modules).filter((m) => !m.up).length;

    if (down === 0) {
      chrome.action.setBadgeText({ text: "" });
    } else {
      chrome.action.setBadgeText({ text: String(down) });
      chrome.action.setBadgeBackgroundColor({ color: "#ea580c" });
    }
  } catch (e) {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "TL_REFRESH_STATUS") {
    updateActionBadge().then(() => sendResponse({ ok: true }));
    return true; // keep the channel open for the async reply
  }
  return false;
});
