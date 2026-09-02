/*
 * instagram.js: reads what is actually rendered on the page.
 *
 * The whole point of the extension: no uploading, no pasting links. Whatever the
 * user is looking at right now is what gets analysed.
 *
 * Instagram ships obfuscated, frequently-rotated CSS class names, so **nothing
 * here keys off a class**. Every selector uses something Instagram cannot change
 * without breaking its own semantics or accessibility:
 *   - <article> wraps a feed post
 *   - <time> marks the timestamp inside it
 *   - <video> is the reel
 *   - href shapes (/p/…, /reel/…, /username/) are the public URL contract
 *   - og: meta tags are the sharing contract
 *
 * When a field cannot be found we return null and let the gateway report it as
 * unchecked. A wrong guess is worse than an honest gap, because the account model
 * would treat a missed follower count as zero and call a real account a bot.
 */
window.TL = window.TL || {};

TL.ig = (function () {
  "use strict";

  const P = TL.parse;

  function text(el) {
    return el ? (el.textContent || "").trim() : "";
  }

  // ----------------------------------------------------------------- //
  // What kind of page is this?
  // ----------------------------------------------------------------- //
  function pageType(url = location.href) {
    const path = new URL(url).pathname;
    if (/^\/(reel|reels|tv)\//.test(path)) return "reel";
    if (/^\/p\//.test(path)) return "post";
    if (path === "/" || /^\/\?/.test(path)) return "feed";
    if (P.usernameFrom(path)) return "profile";
    return "other";
  }

  // ----------------------------------------------------------------- //
  // Post / reel extraction
  // ----------------------------------------------------------------- //

  /** The permalink for a post container, or the page URL when one is open. */
  function permalinkFor(article) {
    if (article) {
      const link = article.querySelector(
        'a[href*="/p/"], a[href*="/reel/"], a[href*="/reels/"], a[href*="/tv/"]'
      );
      if (link && link.href) return link.href;
    }
    const t = pageType();
    if (t === "post" || t === "reel") {
      // og:url holds the *current* reel's canonical URL and Instagram rewrites it
      // as you swipe through the /reels/ feed, even when the address bar stays on
      // "/reels/". Preferring it is what lets each swiped reel get its own badge.
      const og = document.querySelector('meta[property="og:url"]');
      if (og && og.content && /\/(reel|reels|p|tv)\//.test(og.content)) {
        return og.content;
      }
      return location.href;
    }
    return null;
  }

  /**
   * The caption. Instagram renders it differently in feed vs detail views, so
   * try the reliable shapes in order of confidence.
   */
  function captionFor(article) {
    const scope = article || document;

    // 1. On a post/reel page the caption is the page's <h1>.
    const h1 = scope.querySelector("h1");
    if (h1) {
      const t = P.cleanCaption(text(h1));
      if (t.length > 1) return t;
    }

    // 2. og:description carries the caption for the open post, and survives the
    //    DOM being rearranged.
    if (!article) {
      const og = document.querySelector('meta[property="og:description"]');
      if (og && og.content) {
        // Strip the "123 likes, 4 comments - user on date:" preamble Instagram
        // prepends, keeping only the quoted caption body when present.
        const m = og.content.match(/[""](.+)[""]\s*$/s);
        const body = m ? m[1] : og.content;
        const t = P.cleanCaption(body);
        if (t.length > 1 && !/^\d[\d,.\s]*(likes|followers)/i.test(t)) return t;
      }
    }

    // 3. In the feed, the caption sits in the article after the media, usually
    //    the longest span of text that is not a UI control.
    if (article) {
      const spans = Array.from(article.querySelectorAll("span, h1, div[dir='auto']"));
      let best = "";
      for (const s of spans) {
        if (s.querySelector("a, button, svg, span")) continue; // container, not leaf
        const t = P.cleanCaption(text(s));
        if (t.length > best.length && t.length > 15 && !isChrome(t)) best = t;
      }
      if (best) return best;
    }

    return "";
  }

  // UI strings that are not content. Without this the extension classifies
  // Instagram's own furniture.
  const CHROME_WORDS = /^(like|reply|share|follow|following|view all|see more|more|comments?|likes?|translation|view profile|verified|suggested for you|sponsored|paid partnership|original audio|add a comment)/i;

  function isChrome(t) {
    if (CHROME_WORDS.test(t)) return true;
    if (/^\d[\d,.\s]*(likes?|views?|comments?)$/i.test(t)) return true;
    return false;
  }

  /** Any other visible text in the post, alt text on the image, mostly. */
  function onScreenTextFor(article) {
    const scope = article || document;
    const bits = [];
    scope.querySelectorAll("img[alt]").forEach((img) => {
      const alt = (img.alt || "").trim();
      // Instagram writes descriptive alt text ("May be an image of text that
      // says 'GUARANTEED PROFIT'"), which is a free read of burned-in text.
      if (alt.length > 20 && !/^profile picture/i.test(alt)) bits.push(alt);
    });
    return bits.join("\n").slice(0, 2000);
  }

  /** The username that posted it. */
  function authorFor(article) {
    const scope = article || document;
    const links = Array.from(scope.querySelectorAll('header a[href^="/"], a[href^="/"]'));
    for (const a of links) {
      const u = P.usernameFrom(a.getAttribute("href"));
      if (u) return u;
    }
    // Detail pages expose it on the og:title as "user on Instagram: …".
    const ogt = document.querySelector('meta[property="og:title"]');
    if (ogt && ogt.content) {
      const m = ogt.content.match(/^([A-Za-z0-9._]{1,30})\s+on Instagram/);
      if (m) return m[1];
    }
    if (pageType() === "profile") return P.usernameFrom(location.pathname);
    return null;
  }

  function hasVideo(article) {
    const scope = article || document;
    return !!scope.querySelector("video");
  }

  /** Everything the gateway needs about one post. */
  function readPost(article) {
    const url = permalinkFor(article);
    const caption = captionFor(article);
    const onScreen = onScreenTextFor(article);
    const author = authorFor(article);
    const isReel = P.isReelUrl(url || location.href) || hasVideo(article);

    return {
      page_url: url || location.href,
      caption,
      on_screen_text: onScreen,
      is_reel: isReel,
      author,
      key: P.postKey(url || location.href),
    };
  }

  // ----------------------------------------------------------------- //
  // Profile stats — the fake-follower model's inputs
  // ----------------------------------------------------------------- //

  /**
   * Read follower/following/post counts for a username.
   *
   * Only works while a profile page is open, the feed does not render another
   * user's stats. Returns null otherwise, and the gateway then reports the
   * account check as "not checked" rather than inventing zeros.
   */
  function readProfile(username) {
    if (pageType() !== "profile") return null;
    const pageUser = P.usernameFrom(location.pathname);
    if (!pageUser) return null;
    if (username && username.toLowerCase() !== pageUser.toLowerCase()) return null;

    const stats = {};

    // Preferred: the stat links, which carry their number as text.
    const linkFor = (suffix) =>
      document.querySelector(`header a[href$="/${suffix}/"], a[href$="/${suffix}/"]`);

    const followersEl = linkFor("followers");
    const followingEl = linkFor("following");
    if (followersEl) {
      const n = P.parseCount(readStatNumber(followersEl));
      if (n !== null) stats.followers_count = n;
    }
    if (followingEl) {
      const n = P.parseCount(readStatNumber(followingEl));
      if (n !== null) stats.follows_count = n;
    }

    // Posts count has no link; it is the list item containing "posts".
    document.querySelectorAll("header li, header span").forEach((el) => {
      const t = text(el);
      if (/\bposts?\b/i.test(t) && stats.posts_count === undefined) {
        const n = P.parseCount(t);
        if (n !== null) stats.posts_count = n;
      }
    });

    // Fallback for all three: the og:description sentence.
    const og = document.querySelector('meta[property="og:description"]');
    if (og && og.content) {
      const fromMeta = P.parseProfileMeta(og.content);
      for (const k of ["followers_count", "follows_count", "posts_count"]) {
        if (stats[k] === undefined && fromMeta[k] !== undefined) stats[k] = fromMeta[k];
      }
    }

    if (stats.followers_count === undefined && stats.follows_count === undefined) {
      return null; // nothing usable — say so rather than guessing
    }

    const bio = readBio();
    const user = username || pageUser;

    return {
      username: user,
      profile_pic: hasProfilePicture(user) ? 1 : 0,
      username_digit_ratio: P.usernameDigitRatio(user),
      description_length: bio.length,
      private: isPrivate() ? 1 : 0,
      posts_count: stats.posts_count ?? 0,
      followers_count: stats.followers_count ?? 0,
      follows_count: stats.follows_count ?? 0,
    };
  }

  /** A stat link reads "1,234 followers"; prefer its inner number element. */
  function readStatNumber(el) {
    const titled = el.querySelector("[title]");
    if (titled && titled.getAttribute("title")) return titled.getAttribute("title");
    const span = el.querySelector("span span, span");
    if (span) {
      const t = text(span);
      if (/\d/.test(t)) return t;
    }
    return text(el);
  }

  function readBio() {
    // The bio sits in the header, and is the longest non-link text there.
    const header = document.querySelector("header") || document;
    const candidates = Array.from(header.querySelectorAll("span, div[dir='auto'], h1"));
    let best = "";
    for (const c of candidates) {
      if (c.querySelector("a, button, img, svg")) continue;
      const t = text(c);
      if (t.length > best.length && t.length > 3 && !isChrome(t) && !/^\d/.test(t)) best = t;
    }
    return best;
  }

  function hasProfilePicture(username) {
    const img = document.querySelector(
      `header img[alt*="profile picture" i], img[alt*="${username}" i]`
    );
    if (!img) return true; // absence of the node is not evidence of absence
    // Instagram's default avatar is served from a distinctive static path.
    return !/default|anonymous/i.test(img.src || "");
  }

  function isPrivate() {
    return /this account is private/i.test(document.body.innerText || "");
  }

  return {
    pageType,
    readPost,
    readProfile,
    permalinkFor,
    captionFor,
    authorFor,
    hasVideo,
  };
})();
