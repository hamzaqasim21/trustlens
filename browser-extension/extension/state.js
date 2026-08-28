/*
 * state.js: shared runtime state and settings.
 *
 * Loaded first, so everything after it can use window.TL.
 *
 * The cache matters more than it looks: Instagram re-renders the same post many
 * times while you scroll (React remounts nodes constantly), and without a cache
 * keyed on post identity the extension would re-analyse, and on reels,
 * re-transcribe, the same reel repeatedly. That would be both slow and, on a
 * 2-core CPU, genuinely disruptive.
 */
window.TL = window.TL || {};

TL.GATEWAY = "http://127.0.0.1:8100";

TL.settings = {
  enabled: true,
  // Whisper transcription is ~realtime on CPU, so it never runs automatically
  // while scrolling. The user asks for it per-reel with a button.
  autoTranscribe: false,
  // Analyse posts as they scroll into view.
  autoScan: true,
};

// postKey -> { status: "pending"|"done"|"error", verdict, explanation }
TL.cache = new Map();

// Elements already wired, so the observer never double-processes a node.
TL.seen = new WeakSet();

TL.log = (...args) => console.debug("%c[TrustLens]", "color:#7c3aed;font-weight:bold", ...args);

TL.loadSettings = async () => {
  try {
    const stored = await chrome.storage.local.get("settings");
    if (stored && stored.settings) {
      TL.settings = { ...TL.settings, ...stored.settings };
    }
  } catch (e) {
    TL.log("could not load settings, using defaults", e);
  }
  return TL.settings;
};

TL.saveSettings = async (patch) => {
  TL.settings = { ...TL.settings, ...patch };
  try {
    await chrome.storage.local.set({ settings: TL.settings });
  } catch (e) {
    TL.log("could not save settings", e);
  }
  return TL.settings;
};

// React to changes made in the popup without needing a page reload.
try {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.settings) {
      TL.settings = { ...TL.settings, ...changes.settings.newValue };
      TL.log("settings updated", TL.settings);
    }
  });
} catch (e) {
  /* storage listener is a nicety, not a requirement */
}
