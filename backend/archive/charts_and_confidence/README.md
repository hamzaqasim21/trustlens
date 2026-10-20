# Charts (Visual Analytics) + Trust Score confidence — built, then set aside

Built 2026-09-28, taken out of the live app 2026-09-29 at the team's request
(too much to present with hours to go). Nothing here is imported by the
running website or backend. It was never committed to git, which is why it is
kept here instead of deleted.

## What it was
- **Visual Analytics (scope Module 9):** four charts on the Results page —
  fake-account gauge, score-of-each-check list/radar, likes-per-post trend,
  follower-growth timeline — each with a plain-language summary written by
  Gemini (rule-based fallback), plus a bar chart and radar on the Comparison
  page, and chart images inside the scan/comparison PDF reports. Built with
  Recharts (uninstalled from the frontend when this was removed).
- **Trust Score confidence (scope Ethical Considerations):** a confidence %
  on every score (module certainty x evidence coverage, rule-based), marked
  "Uncertain" below 60%, and a "Requires further review" label for scores
  between 35 and 55. Shown on Results, Comparison, the PDFs and the CSV.

## What is in this folder
- `removed_files/` — files that were moved out whole:
  `backend/score_confidence.py`, `backend/chart_explainer.py`,
  `frontend/charts/Charts.jsx` + `Charts.css` (were `frontend/src/components/charts/`).
- `before_removal/` — full copies, taken just before the removal, of every file
  that was *edited* to take the feature out: `scan_service.py`, `main.py`,
  `insights.py`, `reports.py`, `tests/test_dashboard_modules.py`,
  `api/trustlens.js`, `components/ResultExtras.jsx/.css`, `pages/Results.jsx`,
  `pages/Comparison.jsx/.css`, `lib/charting.js`, `package.json`.

## How to bring it back
1. Move `removed_files/` contents back to their original places.
2. Either copy the `before_removal/` files back over the live ones (only safe
   if those files haven't been changed for other reasons since 2026-09-29), or
   re-apply the differences by hand — compare each `before_removal/` file with
   the live one.
3. `cd frontend` then `npm install recharts@^3`.
4. Run the tests: `cd backend` then `.\venv\Scripts\python.exe -m pytest tests -q`.

Still live after the removal (not part of this archive): PDF and CSV export,
the Watch button and watchlist, comparison of 2-4 accounts, the admin console
(whose own charts are separate hand-drawn code and were not touched).
