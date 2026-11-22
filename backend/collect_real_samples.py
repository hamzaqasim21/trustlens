"""
Collects real Instagram data once, saves it to disk, so it can be analysed later
without spending API requests.

For every account in `accounts.py` it saves, as one JSON file in
datasets/instagram_samples/ (gitignored: it is other people's data):
  - profile      (data_ingestion.fetch_instagram_profile)
  - engagement   (data_ingestion.fetch_engagement_data: last 12 posts, captions, likes)
  - comments     (one post's most popular comments, if that post has any)

Safe to stop and restart: accounts that already have a file are skipped
(including accounts that failed, so a missing username is not retried).

Run:  .\venv\Scripts\python.exe collect_real_samples.py [--limit N] [--workers 4]
"""
import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import data_ingestion as di  # noqa: E402  (loads backend/.env)
from accounts import ACCOUNTS  # noqa: E402

OUT = os.path.join(HERE, "datasets", "instagram_samples")
os.makedirs(OUT, exist_ok=True)


def path_for(username):
    return os.path.join(OUT, f"{username}.json")


def collect_one(username, category):
    rec = {"username": username, "category": category, "collected_at": int(time.time())}
    try:
        rec["profile"] = di.fetch_instagram_profile(username)
        if rec["profile"].get("is_private"):
            rec["note"] = "private account: no posts available"
        else:
            rec["engagement"] = di.fetch_engagement_data(username)
            for code, n in zip(rec["engagement"].get("post_codes", []),
                               [p.get("comments", 0) for p in rec["engagement"].get("posts", [])]):
                if n and n > 0:
                    try:
                        rec["comments"] = di.fetch_post_comments(code)
                        rec["comments_post"] = code
                    except Exception as e:  # comments are optional
                        rec["comments_error"] = str(e)[:200]
                    break
    except Exception as e:
        rec["error"] = str(e)[:300]
        rec["trace"] = traceback.format_exc()[-600:]
    # Only a definitive answer is saved ("account does not exist" etc.). A
    # transient failure (timeout, odd reply) is left for the next run to retry.
    definitive = "error" not in rec or "no public Instagram account" in rec["error"]         or "does not exist" in rec["error"]
    if definitive:
        with open(path_for(username), "w", encoding="utf8") as f:
            json.dump(rec, f, ensure_ascii=False)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from-file", help="JSON {username: category} instead of accounts.py")
    a = ap.parse_args()

    todo, seen = [], set()
    if a.from_file:
        groups = {}
        for u, c in json.load(open(a.from_file, encoding="utf8")).items():
            groups.setdefault(c, []).append(u)
    else:
        groups = ACCOUNTS
    for category, names in groups.items():
        for u in names:
            u = u.strip().lstrip("@").lower()
            if u and u not in seen and not os.path.exists(path_for(u)):
                seen.add(u)
                todo.append((u, category))
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} accounts to collect", flush=True)

    ok = bad = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(collect_one, u, c): u for u, c in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            if "error" in rec:
                bad += 1
            else:
                ok += 1
            if i % 10 == 0 or i == len(todo):
                print(f"{i}/{len(todo)}  ok={ok}  failed={bad}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
