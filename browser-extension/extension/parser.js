/*
 * parser.js: pure parsing helpers. No DOM access, no network.
 *
 * Kept separate from instagram.js so this logic can be unit-tested in Node
 * without a browser, and so the fiddly bits (Instagram's "1.2M", Urdu digits,
 * European decimal commas) live in one reviewable place.
 */
window.TL = window.TL || {};
TL.parse = (function () {
  "use strict";

  // Instagram localises counts. These are the digits actually seen on ur/hi/ar
  // locales; without mapping them, an Urdu-locale profile parses as zero
  // followers and the account model then scores a real account as a bot.
  const DIGIT_MAP = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
  };

  function normaliseDigits(str) {
    return String(str).replace(/[٠-٩۰-۹०-९]/g, (d) => DIGIT_MAP[d] || d);
  }

  /**
   * "1,234" -> 1234 · "1.2M" -> 1200000 · "10.5K" -> 10500 · "١٢٣" -> 123
   * Returns null when there is no number to find, which callers must treat as
   * "unknown" rather than zero.
   */
  function parseCount(raw) {
    if (raw === null || raw === undefined) return null;
    let s = normaliseDigits(String(raw)).trim().toLowerCase();
    if (!s) return null;

    const m = s.match(/([\d.,\s]+)\s*([kmb])?/i);
    if (!m) return null;

    let numPart = m[1].replace(/\s/g, "");
    const suffix = m[2];

    if (suffix) {
      // With a K/M/B suffix any separator is a decimal point: "1,2M" = 1.2M.
      numPart = numPart.replace(/,/g, ".");
      const value = parseFloat(numPart);
      if (isNaN(value)) return null;
      const mult = suffix === "k" ? 1e3 : suffix === "m" ? 1e6 : 1e9;
      return Math.round(value * mult);
    }

    // No suffix: separators are thousands grouping ("1,234" / "1.234" / "1 234").
    const digitsOnly = numPart.replace(/[.,]/g, "");
    if (!/^\d+$/.test(digitsOnly)) return null;
    return parseInt(digitsOnly, 10);
  }

  /**
   * Instagram's og:description carries the profile stats in a stable, localised
   * sentence, far more durable than obfuscated CSS classes:
   *   "1,234 Followers, 567 Following, 89 Posts - See Instagram photos…"
   * Returns whichever of the three it could find.
   */
  function parseProfileMeta(description) {
    if (!description) return {};
    const text = normaliseDigits(description);
    const out = {};

    const grab = (words) => {
      for (const w of words) {
        const re = new RegExp("([\\d.,]+\\s*[kmb]?)\\s*" + w, "i");
        const m = text.match(re);
        if (m) return parseCount(m[1]);
      }
      return null;
    };

    const followers = grab(["followers", "follower", "seguidores", "مداح", "فالوورز"]);
    const following = grab(["following", "follows", "siguiendo", "فالوونگ"]);
    const posts = grab(["posts", "post", "publicaciones", "پوسٹس"]);

    if (followers !== null) out.followers_count = followers;
    if (following !== null) out.follows_count = following;
    if (posts !== null) out.posts_count = posts;
    return out;
  }

  /** Digits in the username divided by its length, a model input. */
  function usernameDigitRatio(username) {
    if (!username) return 0;
    const digits = (username.match(/\d/g) || []).length;
    return digits / username.length;
  }

  /**
   * Pull the post/reel shortcode out of any Instagram URL shape.
   * /p/ABC123/ · /reel/ABC123/ · /reels/ABC123/ · /tv/ABC123/
   */
  function shortcodeFrom(url) {
    if (!url) return null;
    const m = String(url).match(/\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
    return m ? m[1] : null;
  }

  function isReelUrl(url) {
    return /\/(reel|reels|tv)\//.test(String(url || ""));
  }

  /** Username from a profile URL, skipping Instagram's own reserved paths. */
  const RESERVED = new Set([
    "p", "reel", "reels", "tv", "explore", "stories", "direct", "accounts",
    "about", "developer", "legal", "privacy", "terms", "your_activity",
    "challenge", "emails", "session", "web", "graphql", "api", "s",
  ]);

  function usernameFrom(url) {
    if (!url) return null;
    let path;
    try {
      path = new URL(url, "https://www.instagram.com").pathname;
    } catch (e) {
      path = String(url);
    }
    const parts = path.split("/").filter(Boolean);
    if (!parts.length) return null;
    const first = parts[0];
    if (RESERVED.has(first.toLowerCase())) return null;
    if (!/^[A-Za-z0-9._]{1,30}$/.test(first)) return null;
    return first;
  }

  /**
   * Strip the chrome Instagram bakes into caption nodes, the trailing
   * "more"/"…more" affordance and collapsed whitespace. Left in, "more" would be
   * classified as part of the caption text.
   */
  function cleanCaption(text) {
    if (!text) return "";
    return String(text)
      .replace(/ /g, " ")
      .replace(/\s*(?:…|\.\.\.)?\s*\bmore\b\s*$/i, "")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  /** Identity for the cache: shortcode when there is one, else the URL. */
  function postKey(url) {
    return shortcodeFrom(url) || String(url || "").split("?")[0];
  }

  return {
    parseCount,
    parseProfileMeta,
    usernameDigitRatio,
    shortcodeFrom,
    isReelUrl,
    usernameFrom,
    cleanCaption,
    postKey,
    normaliseDigits,
  };
})();
