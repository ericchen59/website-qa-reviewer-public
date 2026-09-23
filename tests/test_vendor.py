import unittest

from qa_review.fetch_policy import PolicyError, check_url, guarded
from qa_review.vendor import vendor_html

PUBLIC = lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]


class PolicyTests(unittest.TestCase):
    def test_rejects_loopback_private_linklocal_and_non_http(self):
        for url in ("http://127.0.0.1/a.css", "http://localhost/a.css", "http://10.0.0.5/a.css",
                    "http://192.168.1.2/a.css", "http://169.254.169.254/latest", "file:///etc/passwd",
                    "ftp://example.com/a.css", "javascript:alert(1)"):
            with self.assertRaises(PolicyError, msg=url):
                check_url(url, resolve=PUBLIC if url.startswith("http://example") else None)

    def test_hostname_resolving_to_private_address_is_rejected(self):
        private = lambda host, *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))]
        with self.assertRaises(PolicyError):
            check_url("https://evil.example/a.css", resolve=private)

    def test_public_https_passes(self):
        check_url("https://cdn.example.com/a.css", resolve=PUBLIC)

    def test_shared_address_space_is_rejected(self):
        # security:fetch_policy.py:56 -- 100.64.0.0/10 (CGNAT, Tailscale) is not flagged by
        # ipaddress.is_private, so the old enumerated-flags check let it through.
        with self.assertRaises(PolicyError):
            check_url("http://100.64.0.1/a.css")

    def test_multicast_is_still_rejected_even_though_is_global_says_true(self):
        # ipaddress.is_global counts some multicast ranges as "global"; multicast must stay
        # an explicit block regardless.
        with self.assertRaises(PolicyError):
            check_url("http://224.0.0.1/a.css")

    def test_redirect_to_private_address_is_rejected(self):
        base = lambda url: ("http://10.0.0.1/secret.css", b"x")
        with self.assertRaises(PolicyError):
            guarded(base, resolve=PUBLIC)("https://cdn.example.com/a.css")

    def test_caps_on_count_and_size(self):
        base = lambda url: (url, b"x" * 100)
        g = guarded(base, resolve=PUBLIC, max_count=2, max_bytes=250)
        g("https://a.example/1.css")
        g("https://a.example/2.css")
        with self.assertRaises(PolicyError):
            g("https://a.example/3.css")
        g2 = guarded(base, resolve=PUBLIC, max_count=10, max_bytes=150)
        g2("https://a.example/1.css")
        with self.assertRaises(PolicyError):
            g2("https://a.example/2.css")


HTML = """<html><head><title>T</title>
<link rel="stylesheet" href="/a.css"><link rel="icon" href="/i.ico">
<base href="http://evil/"><meta http-equiv="refresh" content="0;url=http://x">
<script>alert(1)</script><script src="x.js"></script></head>
<body onload="steal()"><a href="javascript:evil()" onclick="x()">go</a>
<iframe src="http://x"></iframe><object data="x"></object><embed src="x">
<input type="hidden" name="csrf" value="SECRET"><input type="text" value="typed">
<input type="submit" value="Buy now"><textarea>private note</textarea><p>Visible copy</p></body></html>"""


class VendorTests(unittest.TestCase):
    def fetch(self, url):
        if url.endswith("a.css"):
            return b"p{color:red} .x{background:url(/img/bg.png)} @import url(/b.css);"
        if url.endswith("b.css"):
            return b"h1{color:blue}"
        if url.endswith("bg.png"):
            return b"\x89PNGDATA"
        raise IOError("unexpected " + url)

    def test_inlines_stylesheet_and_assets_and_reports_vendored(self):
        out, ok, notes = vendor_html(HTML, self.fetch, base_url="https://site.example/page/")
        self.assertTrue(ok, notes)
        self.assertIn("<style", out)
        self.assertIn("color:red", out)
        self.assertIn("color:blue", out)                 # @import inlined
        self.assertIn("data:image/png;base64,", out)     # url() asset inlined
        self.assertNotIn('href="/a.css"', out)

    def test_strips_active_content(self):
        out, _, _ = vendor_html(HTML, self.fetch, base_url="https://site.example/")
        for bad in ("<script", "onload", "onclick", "javascript:", "<iframe", "<object", "<embed",
                    "<base", "refresh", "SECRET", "typed", "private note"):
            self.assertNotIn(bad, out, bad)
        self.assertIn("Visible copy", out)
        self.assertIn('value="Buy now"', out)            # button labels are copy

    def test_the_snapshot_carries_a_csp_as_a_backstop_for_the_regex_stripper(self):
        # security:vendor.py:29 -- regex stripping is inherently incomplete; the CSP blocks
        # scripts/frames structurally regardless of what slipped past it.
        out, _, _ = vendor_html(HTML, self.fetch, base_url="https://site.example/")
        self.assertIn("Content-Security-Policy", out)
        self.assertIn("default-src 'none'", out)
        self.assertIn("style-src 'unsafe-inline'", out)   # or the vendored CSS wouldn't apply

    def test_bypasses_of_the_regex_stripper_are_closed(self):
        # adversarial/security:vendor.py:29 -- reproduced bypasses: "/" instead of whitespace
        # before an event handler, a closing tag carrying its own attributes, and an unpaired
        # opening tag with no matching close.
        html = ('<svg/onload=alert(1)><script>x()</script foo>'
               '<iframe src="file:///etc/hosts">')
        out, _, _ = vendor_html(html, self.fetch, base_url="https://site.example/")
        self.assertNotIn("onload", out)
        self.assertNotIn("<script", out)
        self.assertNotIn("<iframe", out)

    def test_failed_stylesheet_fetch_marks_styles_not_vendored(self):
        def failing(url):
            raise IOError("403")
        out, ok, notes = vendor_html(HTML, failing, base_url="https://site.example/")
        self.assertFalse(ok)
        self.assertTrue(notes)
        self.assertNotIn("<link rel=\"stylesheet\"", out)

    def test_no_external_stylesheet_counts_as_vendored(self):
        out, ok, _ = vendor_html("<html><body><p>x</p></body></html>", self.fetch)
        self.assertTrue(ok)


    def test_asset_requests_have_their_own_budget_and_never_starve_stylesheets(self):
        css = b"".join(b".a%d{background:url(/img/%d.png)}" % (i, i) for i in range(8))
        html = '<html><head><link rel="stylesheet" href="/a.css"><link rel="stylesheet" href="/b.css"></head></html>'
        sheets = guarded(lambda u: (u, css), resolve=PUBLIC, max_count=2)
        assets = guarded(lambda u: (u, b"PNG"), resolve=PUBLIC, max_count=100)
        out, ok, notes = vendor_html(html, sheets, base_url="https://site.example/", fetch_asset=assets)
        self.assertTrue(ok, notes)
        self.assertEqual(out.count("data:image/png;base64,"), 16)

    def test_asset_failures_do_not_mark_styles_as_not_vendored(self):
        def no_assets(url):
            raise IOError("blocked")
        html = '<html><head><link rel="stylesheet" href="/a.css"></head></html>'
        out, ok, _ = vendor_html(html, lambda u: b"p{background:url(/x.png)}", base_url="https://s.example/",
                                 fetch_asset=no_assets)
        self.assertTrue(ok)

    def test_a_failed_at_import_marks_styles_not_vendored(self):
        # adversarial:vendor.py:71 -- a failed @import used to be silently dropped (empty
        # string), leaving ok=True even though a rule -- possibly a visibility-hiding one --
        # never made it into the snapshot a structural condition trusts as "visible on load".
        def fetch(url):
            if url.endswith("a.css"):
                return b"@import url(/hidden-rule.css); p{color:red}"
            raise IOError("403")
        html = '<html><head><link rel="stylesheet" href="/a.css"></head></html>'
        out, ok, notes = vendor_html(html, fetch, base_url="https://site.example/")
        self.assertFalse(ok)
        self.assertTrue(any("@import" in n for n in notes), notes)
        self.assertIn("color:red", out)   # the rest of the sheet still inlines

    def test_inline_style_with_at_import_marks_styles_not_vendored(self):
        # Only <link> sheets are inlined -- an inline <style>@import ...</style> is left
        # untouched and silently never resolves once the offline render blocks the network.
        html = '<html><head><style>@import url("/hidden.css");</style></head><body>x</body></html>'
        out, ok, notes = vendor_html(html, self.fetch, base_url="https://site.example/")
        self.assertFalse(ok)
        self.assertTrue(any("inline" in n and "@import" in n for n in notes), notes)

    def test_a_case_insensitive_style_close_tag_cannot_inject_a_script(self):
        # security:vendor.py:118 -- only the lowercase "</style" was escaped, so fetched CSS
        # (attacker-controlled: any host that passes the fetch policy) containing "</STYLE>"
        # closed the tag early and a live <script> after it ran in the offline render, whose
        # DOM and screenshot are trusted for verdicts.
        def fetch(url):
            return b"a{}</STYLE><script>window.PWNED=1</script><style>"
        html = '<link rel="stylesheet" href="a.css">'
        out, ok, notes = vendor_html(html, fetch, base_url="https://site.example/")
        self.assertNotIn("</STYLE>", out)          # the closing tag must not survive unescaped
        self.assertIn("<\\/STYLE>", out)           # it's neutralized to inert text instead


if __name__ == "__main__":
    unittest.main()
