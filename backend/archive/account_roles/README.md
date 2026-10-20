# Account roles (Creator / Brand) — built, then set aside before the demo

Built 2026-09-28, taken out of the live app 2026-09-29 at Hamza's request (too
much to present with a few hours to go; to be added back later). Nothing here is
imported by the running website.

What it was:
- **Sign-up account type** (Personal / Creator / Brand), changeable in Settings.
- **Brand tools** (`BrandTools.jsx`, `brand.py`): bulk analysis of up to 10
  accounts, API keys (stored as SHA-256 hashes) and `POST /api/v1/analyze`.
- **Creator studio** (`CreatorStudio.jsx`, `creator.py`): ownership proven by a
  code in the Instagram bio, audience report, tips, Trust Badge certificate PDF
  (`badge_certificate_pdf.py`) checkable at `/badge/<code>` (`BadgeVerify.jsx`).
- Tests: `tests_removed.py`.

To bring it back: move the files to their old places (backend files to
`backend/`, frontend files to `frontend/src/pages|components|lib/`), re-add in
`main.py` `import creator, brand` + `app.include_router(...)`, re-add
`User.account_type` and the `ApiKey` / `CreatorClaim` / `TrustBadge` models in
`database.py`, the routes in `App.jsx`, the picker in `SignUp.jsx` / `Settings.jsx`,
and the API calls in `api/trustlens.js`. The database tables and the
`users.account_type` column still exist in `trustlens.db`, unused.

Still live (not part of this archive): watchlist + alerts, comparison of 2-4
accounts with PDF/CSV, scan PDF report, CSV export, visual analytics, confidence.
