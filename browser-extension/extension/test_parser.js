/*
 * Node test for parser.js, no browser needed.
 *   node test_parser.js
 *
 * Covers the formats Instagram actually emits, including the localised digits
 * that silently zero out a profile's stats if unhandled.
 */
const fs = require("fs");
const path = require("path");

// parser.js expects a browser global; give it one and eval it.
global.window = {};
eval(fs.readFileSync(path.join(__dirname, "parser.js"), "utf8"));
const P = global.window.TL.parse;

let pass = 0, fail = 0;
function eq(actual, expected, label) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; console.log(`  ok   ${label}`); }
  else { fail++; console.log(`  FAIL ${label}\n         expected ${e}\n         got      ${a}`); }
}

console.log("\nparseCount");
eq(P.parseCount("1,234"), 1234, "comma thousands");
eq(P.parseCount("1.2M"), 1200000, "millions");
eq(P.parseCount("10.5K"), 10500, "thousands with decimal");
eq(P.parseCount("1.234"), 1234, "dot as thousands separator");
eq(P.parseCount("1,2M"), 1200000, "european decimal with suffix");
eq(P.parseCount("523"), 523, "plain");
eq(P.parseCount("1 234"), 1234, "space separator");
eq(P.parseCount("١٢٣"), 123, "arabic-indic digits");
eq(P.parseCount("۴۵۶"), 456, "urdu/persian digits");
eq(P.parseCount("२,५००"), 2500, "devanagari digits");
eq(P.parseCount(""), null, "empty is null not zero");
eq(P.parseCount("no digits"), null, "text is null");
eq(P.parseCount("2,847 posts"), 2847, "count with trailing word");

console.log("\nparseProfileMeta");
eq(P.parseProfileMeta("1,234 Followers, 567 Following, 89 Posts - See Instagram photos"),
   { followers_count: 1234, follows_count: 567, posts_count: 89 }, "standard english meta");
eq(P.parseProfileMeta("1.2M Followers, 340 Following, 1,205 Posts"),
   { followers_count: 1200000, follows_count: 340, posts_count: 1205 }, "abbreviated followers");
eq(P.parseProfileMeta(""), {}, "empty meta");
eq(P.parseProfileMeta("no numbers here"), {}, "unparseable meta");

console.log("\nusernameDigitRatio");
eq(P.usernameDigitRatio("ali_ahmad"), 0, "no digits");
eq(P.usernameDigitRatio("user1234"), 0.5, "half digits");
eq(P.usernameDigitRatio(""), 0, "empty");

console.log("\nshortcode / reel detection");
eq(P.shortcodeFrom("https://www.instagram.com/p/CxYz123_-/"), "CxYz123_-", "post");
eq(P.shortcodeFrom("https://www.instagram.com/reel/ABC123/?utm=1"), "ABC123", "reel with query");
eq(P.shortcodeFrom("https://www.instagram.com/reels/XYZ789/"), "XYZ789", "reels plural");
eq(P.shortcodeFrom("https://www.instagram.com/aliahmad/"), null, "profile has none");
eq(P.isReelUrl("https://www.instagram.com/reel/ABC/"), true, "is reel");
eq(P.isReelUrl("https://www.instagram.com/p/ABC/"), false, "post is not reel");

console.log("\nusernameFrom");
eq(P.usernameFrom("https://www.instagram.com/ali.ahmad_1/"), "ali.ahmad_1", "profile url");
eq(P.usernameFrom("/p/ABC123/"), null, "post path is not a username");
eq(P.usernameFrom("/explore/tags/food/"), null, "reserved path rejected");
eq(P.usernameFrom("/reels/ABC/"), null, "reels path rejected");
eq(P.usernameFrom("https://www.instagram.com/"), null, "root");

console.log("\ncleanCaption");
eq(P.cleanCaption("Buy now!  … more"), "Buy now!", "strips trailing more");
eq(P.cleanCaption("line\n\n\n\nline2"), "line\n\nline2", "collapses blank lines");
eq(P.cleanCaption("  spaced   out  "), "spaced out", "trims and collapses");
eq(P.cleanCaption("nothing to strip"), "nothing to strip", "leaves clean text");

console.log("\npostKey");
eq(P.postKey("https://www.instagram.com/reel/ABC/?x=1"), "ABC", "reel key is shortcode");
eq(P.postKey("https://www.instagram.com/aliahmad/?hl=en"),
   "https://www.instagram.com/aliahmad/", "profile key drops query");

console.log(`\n${pass} passed, ${fail} failed\n`);
process.exit(fail ? 1 : 0);
