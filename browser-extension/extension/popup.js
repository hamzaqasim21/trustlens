/*
 * popup.js: the toolbar panel.
 *
 * Its main job is diagnosis. Four separate services have to be running for the
 * full verdict, so when something looks wrong the first question is always
 * "which piece is down?". This answers that without a terminal.
 */
const GATEWAY = "http://127.0.0.1:8100";

function setDot(id, up, label) {
  const dot = document.getElementById("d-" + id);
  const txt = document.getElementById("s-" + id);
  if (dot) dot.className = "dot " + (up ? "up" : "down");
  if (txt) txt.textContent = label;
}

async function refresh() {
  const hint = document.getElementById("hint");
  hint.textContent = "";

  try {
    const res = await fetch(`${GATEWAY}/health`, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    setDot("gateway", true, "up");

    const modules = data.modules || {};
    for (const key of ["classifier", "account_model", "transcriber"]) {
      const m = modules[key] || {};
      setDot(key, !!m.up, m.up ? "up" : "down");
    }

    setDot("gemini", !!data.gemini_configured,
           data.gemini_configured ? "ready" : "no key");

    const down = Object.entries(modules).filter(([, m]) => !m.up).map(([k]) => k);
    if (down.length) {
      hint.textContent = "Down: " + down.join(", ") +
        ". Those checks are skipped; the rest still work.";
    } else if (!data.gemini_configured) {
      hint.textContent = "No Gemini key — explanations use built-in wording. " +
        "Add GEMINI_API_KEY to gateway/.env for richer ones.";
    } else {
      hint.textContent = "All services ready.";
    }
  } catch (err) {
    setDot("gateway", false, "down");
    ["classifier", "account_model", "transcriber", "gemini"]
      .forEach((k) => setDot(k, false, "—"));
    document.getElementById("hint").textContent =
      "Gateway not running. Start it, then press Re-check.";
  }

  try {
    chrome.runtime.sendMessage({ type: "TL_REFRESH_STATUS" });
  } catch (e) { /* worker may be asleep; harmless */ }
}

async function loadSettings() {
  const { settings } = await chrome.storage.local.get("settings");
  const s = settings || { enabled: true, autoScan: true };
  document.getElementById("enabled").checked = s.enabled !== false;
  document.getElementById("autoScan").checked = s.autoScan !== false;
}

async function saveSettings() {
  const settings = {
    enabled: document.getElementById("enabled").checked,
    autoScan: document.getElementById("autoScan").checked,
  };
  await chrome.storage.local.set({ settings });
}

document.getElementById("enabled").addEventListener("change", saveSettings);
document.getElementById("autoScan").addEventListener("change", saveSettings);

document.getElementById("refresh").addEventListener("click", refresh);

document.getElementById("scan").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\/www\.instagram\.com/.test(tab.url || "")) {
    document.getElementById("hint").textContent = "Open instagram.com first.";
    return;
  }
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "TL_SCAN_NOW" });
    window.close();
  } catch (e) {
    document.getElementById("hint").textContent =
      "Reload the Instagram tab, then try again.";
  }
});

loadSettings();
refresh();
