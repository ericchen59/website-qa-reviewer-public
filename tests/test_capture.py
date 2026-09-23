import types
import unittest

from qa_review.capture import CaptureError, _browser_fetch, _wait_past_challenge
from qa_review.fetch_policy import PolicyError


class FakePage:
    """A stand-in for a Playwright page: title() advances one step per wait_for_timeout call."""

    def __init__(self, titles):
        self.titles = list(titles)
        self.waits = 0

    def title(self):
        return self.titles[min(self.waits, len(self.titles) - 1)]

    def wait_for_timeout(self, ms):
        self.waits += 1


class ChallengeWaitTests(unittest.TestCase):
    def test_clears_immediately_when_the_title_is_not_a_challenge(self):
        page = FakePage(["Widget Deluxe 2026 | Shop"])
        _wait_past_challenge(page)   # must not raise
        self.assertEqual(page.waits, 0)

    def test_clears_after_a_few_waits(self):
        page = FakePage(["Just a moment...", "Checking your browser", "Widget Deluxe 2026 | Shop"])
        _wait_past_challenge(page)   # must not raise
        self.assertEqual(page.waits, 2)

    def test_raises_capture_error_when_the_challenge_never_clears(self):
        page = FakePage(["Just a moment..."])
        with self.assertRaises(CaptureError) as cm:
            _wait_past_challenge(page)
        self.assertIn("bot-protection challenge", str(cm.exception))
        self.assertIn("qa login", str(cm.exception))
        self.assertEqual(page.waits, 20)


class FakeResponse:
    def __init__(self, status, headers=None, body=b"data"):
        self.status = status
        self.headers = headers or {}
        self._body = body

    @property
    def ok(self):
        return 200 <= self.status < 300

    def body(self):
        return self._body


class FakeClient:
    """A stand-in for Playwright's APIRequestContext, keyed by exact URL."""

    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    def get(self, url, max_redirects=0, timeout=None):
        self.requested.append(url)
        return self.responses[url]


class FakePlaywright:
    def __init__(self, client):
        self.request = types.SimpleNamespace(new_context=lambda: client)


class RedirectSafetyTests(unittest.TestCase):
    """security:fetch_policy.py:56 -- a redirect must be policy-checked before it's requested,
    not just after: letting the request library auto-follow it reaches the blocked address
    first and only discards the response, which is a blind SSRF. IP literals throughout so
    the test never depends on real DNS resolution."""

    def _fetch(self, client):
        p = FakePlaywright(client)
        ctx = types.SimpleNamespace(request=client)
        sheets, _ = _browser_fetch(p, ctx, page_url="https://93.184.216.34/page/")
        return sheets

    def test_a_redirect_to_a_private_address_is_rejected_before_being_requested(self):
        client = FakeClient({
            "https://93.184.216.34/a.css":
                FakeResponse(302, headers={"location": "http://127.0.0.1:9999/internal"}),
        })
        fetch = self._fetch(client)
        with self.assertRaises(PolicyError):
            fetch("https://93.184.216.34/a.css")
        # the redirect target must never actually have been requested
        self.assertEqual(client.requested, ["https://93.184.216.34/a.css"])

    def test_a_redirect_to_a_cloud_metadata_address_is_rejected(self):
        client = FakeClient({
            "https://93.184.216.34/a.css":
                FakeResponse(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}),
        })
        fetch = self._fetch(client)
        with self.assertRaises(PolicyError):
            fetch("https://93.184.216.34/a.css")
        self.assertEqual(client.requested, ["https://93.184.216.34/a.css"])

    def test_redirects_to_public_addresses_are_followed_hop_by_hop(self):
        client = FakeClient({
            "https://93.184.216.34/a.css":
                FakeResponse(302, headers={"location": "https://151.101.1.69/a.css"}),
            "https://151.101.1.69/a.css": FakeResponse(200, body=b"p{color:red}"),
        })
        fetch = self._fetch(client)
        data = fetch("https://93.184.216.34/a.css")
        self.assertEqual(data, b"p{color:red}")
        self.assertEqual(client.requested,
                         ["https://93.184.216.34/a.css", "https://151.101.1.69/a.css"])

    def test_a_shared_address_space_target_is_blocked(self):
        # 100.64.0.0/10 (CGNAT, Tailscale): is_private doesn't flag it, is_global does.
        client = FakeClient({
            "https://93.184.216.34/a.css":
                FakeResponse(302, headers={"location": "http://100.64.0.1/internal"}),
        })
        fetch = self._fetch(client)
        with self.assertRaises(PolicyError):
            fetch("https://93.184.216.34/a.css")


if __name__ == "__main__":
    unittest.main()
