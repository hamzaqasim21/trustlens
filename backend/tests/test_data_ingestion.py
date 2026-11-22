"""The RapidAPI wrapper must survive the provider's occasional odd replies."""
import pytest
import requests

import data_ingestion as di


class FakeResponse:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


def _script(monkeypatch, outcomes):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        o = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(di.requests, "post", fake_post)
    return calls


def test_list_reply_is_retried_once_then_works(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse([]), FakeResponse({"posts": []})])
    r = di._post_with_retry("u", {}, {}, 5, "Instagram posts API")
    assert r.json() == {"posts": []} and len(calls) == 2


def test_list_reply_twice_gives_a_clear_error_not_a_crash(monkeypatch):
    _script(monkeypatch, [FakeResponse([]), FakeResponse([])])
    with pytest.raises(Exception, match="unexpected reply"):
        di._post_with_retry("u", {}, {}, 5, "Instagram posts API")


def test_connection_reset_is_retried(monkeypatch):
    calls = _script(monkeypatch, [requests.exceptions.ConnectionError("reset"), FakeResponse({"ok": 1})])
    assert di._post_with_retry("u", {}, {}, 5, "x").json() == {"ok": 1} and len(calls) == 2


def test_missing_account_reply_is_not_retried(monkeypatch):
    calls = _script(monkeypatch, [FakeResponse({"error": "does not exist"})])
    di._post_with_retry("u", {}, {}, 5, "x")
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# The provider being rate-limited by Instagram ("429 Too Many Requests")
# --------------------------------------------------------------------------- #
BUSY = {"error": "Profile data not found. Received 429 Too Many Requests."}
PROFILE = {"username": "leomessi", "follower_count": 517793028, "following_count": 300,
           "media_count": 1300, "biography": "", "full_name": "Leo Messi", "is_verified": True}


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(di, "BUSY_WAITS", (0, 0))
    monkeypatch.setattr(di.time, "sleep", lambda s: None)


def test_busy_provider_is_retried_and_the_profile_loads(monkeypatch, no_wait):
    calls = _script(monkeypatch, [FakeResponse(BUSY), FakeResponse(BUSY), FakeResponse(PROFILE)])
    assert di.fetch_instagram_profile("leomessi")["followers"] == 517793028
    assert len(calls) == 3


def test_still_busy_after_retries_says_so_clearly(monkeypatch, no_wait):
    _script(monkeypatch, [FakeResponse(BUSY)])
    with pytest.raises(Exception, match="too many requests") as e:
        di.fetch_instagram_profile("leomessi")
    assert not isinstance(e.value, di.ProfileNotFoundError)    # not "check the spelling"


def test_account_that_does_not_exist_is_not_retried(monkeypatch, no_wait):
    calls = _script(monkeypatch, [FakeResponse({"error": "Invalid or missing username or user does not exist on Instagram"})])
    with pytest.raises(di.ProfileNotFoundError):
        di.fetch_instagram_profile("nobody_here_123")
    assert len(calls) == 1


def test_posts_error_is_reported_not_read_as_zero_posts(monkeypatch, no_wait):
    _script(monkeypatch, [FakeResponse(BUSY)])
    with pytest.raises(Exception, match="too many requests"):
        di.fetch_engagement_data("leomessi")


def test_private_or_empty_account_still_reads_as_no_posts(monkeypatch, no_wait):
    _script(monkeypatch, [FakeResponse({"posts": [], "pagination_token": None})])
    e = di.fetch_engagement_data("private.person")
    assert e["posts_analyzed"] == 0 and e["reel_media"] == []
