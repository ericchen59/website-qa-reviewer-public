"""Page capture: a self-contained snapshot, text blocks with visibility and boxes, a screenshot.

A live URL is fetched in a headed Chrome with a persistent, owner-only profile (mirroring
fixtures/capture.js: headless is challenged by bot protection). Either way the snapshot is
vendored (styles and assets inlined, active content stripped) and then rendered from disk in
Chromium with every network request blocked, so a live capture and a saved fixture take the
same path.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import stat
from urllib.parse import urljoin, urlsplit

from .fetch_policy import check_url, guarded
from .schema import PageBlock
from .ids import slugify
from .vendor import vendor_html

JS = (pathlib.Path(__file__).parent / "js" / "blocks.js").read_text(encoding="utf-8")
VIEWPORT = {"width": 1440, "height": 900}
CHANNEL = os.environ.get("QA_REVIEW_BROWSER_CHANNEL", "chrome")
DEFAULT_PROFILE = pathlib.Path.home() / ".qa-review" / "profile"
PROFILE_MARKER = ".qa-review-profile"      # proves `clean --profile` owns this directory


def profile_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("QA_REVIEW_PROFILE", DEFAULT_PROFILE))


def profile_dir() -> pathlib.Path:
    p = profile_path()
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, stat.S_IRWXU)          # owner only: the profile holds login credentials
    (p / PROFILE_MARKER).touch(exist_ok=True)
    return p


def _is_url(source: str) -> bool:
    return bool(re.match(r"https?://", source))


def page_key(source: str) -> str:
    if _is_url(source):
        u = urlsplit(source)
        return slugify(u.netloc + u.path)
    return slugify(pathlib.Path(source).stem)


def _only_local(route):
    if route.request.url.startswith("file:"):
        route.continue_()
    else:
        route.abort()


@contextlib.contextmanager
def offline_page(snapshot):
    """The snapshot opened from disk in headless Chromium with every network request blocked.
    The one place the offline guarantee is set up: captures and the overlay both use it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=CHANNEL, headless=True)
        try:
            ctx = browser.new_context(viewport=VIEWPORT)
            ctx.route("**/*", _only_local)
            page = ctx.new_page()
            page.goto(pathlib.Path(snapshot).resolve().as_uri(), wait_until="load")
            yield page
        finally:
            browser.close()


def render_snapshot(snapshot: pathlib.Path, styles_vendored: bool, screenshot: bool = True):
    """Render the snapshot from disk with the network blocked; return (blocks, png bytes|None)."""
    with offline_page(snapshot) as page:
        raw = page.evaluate(JS, styles_vendored)
        png = page.screenshot(full_page=True) if screenshot and styles_vendored else None
    blocks = [PageBlock(index=i, **b) for i, b in enumerate(raw)]
    return blocks, png


class CaptureError(RuntimeError):
    """The captured page is not the real page (a bot-protection challenge never cleared)."""


def _no_fetch(url):
    raise IOError("no fetcher available for a saved page")


def _has_external_styles(html: str) -> bool:
    return bool(re.search(r"<link\b[^>]*rel\s*=\s*[\"']?[^\"'>]*stylesheet", html, re.I))


_CHALLENGE = re.compile(r"just a moment|attention required|checking", re.I)


def _wait_past_challenge(page) -> None:
    """Give a bot-protection interstitial time to clear (headless is challenged, headed usually is
    not). Raises CaptureError if it is still showing after the wait, so a login or CAPTCHA page is
    never silently reviewed as if it were the real page (its text mostly won't match the checklist,
    producing a confident-looking NOT FOUND ON PAGE report about the wrong page)."""
    for _ in range(20):
        if not _CHALLENGE.search(page.title()):
            return
        page.wait_for_timeout(1000)
    raise CaptureError(
        f"the page still looks like a bot-protection challenge after 20s (title: {page.title()!r}). "
        "Run `qa login <url>` once to establish a session in the saved browser profile, or pass a "
        "saved .html file instead.")


def login(url: str) -> None:
    """Open the persistent profile headed at `url` and wait for the user to finish logging in.
    The session is saved to the same profile `capture` and `vendor_file` reuse."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _open_profile(p)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            input(f"Log in at {url} in the Chrome window that just opened, then press Enter here "
                  "to save the session... ")
        finally:
            ctx.close()


def _open_profile(p):
    return p.chromium.launch_persistent_context(
        str(profile_dir()), channel=CHANNEL, headless=False, viewport=VIEWPORT,
        locale="en-US", timezone_id="America/New_York")


def _browser_fetch(p, ctx, page_url: str):
    """A guarded fetcher: the logged-in session for the page's own origin, cookieless otherwise.

    Redirects are followed one hop at a time (max_redirects=0) with every hop -- not just the
    final URL -- checked against the fetch policy before it's requested. Letting the request
    library auto-follow redirects would mean it reaches a blocked address (127.0.0.1, a cloud
    metadata IP) before the policy's post-hoc check on the final URL ever ran: a blind SSRF.
    """
    origin = urlsplit(page_url)[:2]
    anon = p.request.new_context()

    def fetch(u):
        check_url(u)
        client = ctx.request if urlsplit(u)[:2] == origin else anon
        for _ in range(4):     # the request itself, plus up to 3 redirect hops
            r = client.get(u, max_redirects=0, timeout=20000)
            if r.status in (301, 302, 303, 307, 308):
                loc = r.headers.get("location")
                if not loc:
                    raise IOError(f"redirect from {u} has no Location header")
                u = urljoin(u, loc)
                check_url(u)
                continue
            if not r.ok:
                raise IOError(f"{r.status} for {u}")
            return u, r.body()
        raise IOError(f"too many redirects from {u}")

    # stylesheets and their url() assets get separate request budgets
    return guarded(fetch, max_count=60), guarded(fetch, max_count=600, max_bytes=8_000_000)


def _capture_live(url: str):
    """Fetch the rendered DOM in headed Chrome and vendor it while the session is open."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _open_profile(p)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _wait_past_challenge(page)
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            html, final = page.content(), page.url
            sheets, assets = _browser_fetch(p, ctx, final)
            vendored, ok, notes = vendor_html(html, sheets, base_url=final, fetch_asset=assets)
            return vendored, ok, notes
        finally:
            ctx.close()


def vendor_file(html_path, out_path, base_url: str) -> tuple[bool, list[str]]:
    """Vendor a saved page using the logged-in browser profile (for fixtures). base_url is
    where the page was captured from, needed to resolve its stylesheet links."""
    from playwright.sync_api import sync_playwright

    html = pathlib.Path(html_path).read_text(encoding="utf-8", errors="replace")
    with sync_playwright() as p:
        ctx = _open_profile(p)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)   # pass the bot challenge
            _wait_past_challenge(page)
            sheets, assets = _browser_fetch(p, ctx, base_url)
            out, ok, notes = vendor_html(html, sheets, base_url=base_url, fetch_asset=assets)
        finally:
            ctx.close()
    pathlib.Path(out_path).write_text(out, encoding="utf-8")
    return ok, notes


def capture(source: str, run_dir, screenshot: bool = True) -> dict:
    """Capture `source` (URL or saved HTML file) into run_dir and return the capture record."""
    run_dir = pathlib.Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    live = _is_url(source)
    if live:
        vendored_html, ok, notes = _capture_live(source)
    else:
        html = pathlib.Path(source).read_text(encoding="utf-8", errors="replace")
        vendored_html, ok, notes = vendor_html(html, _no_fetch)
        if not _has_external_styles(html):
            ok, notes = True, []
    snapshot = run_dir / "snapshot.html"
    snapshot.write_text(vendored_html, encoding="utf-8")
    blocks, png = render_snapshot(snapshot, ok, screenshot)
    if png:
        (run_dir / "screenshot.png").write_bytes(png)
    (run_dir / "blocks.json").write_text(json.dumps([b.to_dict() for b in blocks], indent=1), encoding="utf-8")
    meta = {"kind": "url" if live else "file", "source": source, "key": page_key(source),
            "snapshot": "snapshot.html", "styles_vendored": ok, "notes": notes}
    (run_dir / "capture.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["blocks"] = blocks
    return meta
