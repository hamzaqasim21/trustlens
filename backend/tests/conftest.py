import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Tests must never send real email or start the background watchlist re-check.
os.environ.setdefault("TRUSTLENS_DISABLE_EMAIL", "1")
os.environ.setdefault("TRUSTLENS_DISABLE_BACKGROUND", "1")
