"""Make a page snapshot self-contained and inert.

Pure function over the HTML and a fetcher: stylesheets and their url() assets are inlined,
and active content is stripped (scripts, iframes, objects, embeds, <base>, meta refresh,
inline event handlers, javascript: links, form values). Returns (html, styles_vendored, notes);
styles_vendored is False when any stylesheet could not be fetched.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from urllib.parse import urljoin

_LINK = re.compile(r"<link\b[^>]*>", re.I)
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.I | re.S)
_ATTR = lambda name: re.compile(r"\b" + name + r"\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
_IMPORT = re.compile(r"@import\s+(?:url\(\s*(['\"]?)(.*?)\1\s*\)|(['\"])(.*?)\3)\s*[^;]*;", re.I)
_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.I)
_HTML_OPEN = re.compile(r"<html\b[^>]*>", re.I)
_CSP_META = ('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'style-src \'unsafe-inline\'; img-src data:; font-src data:">')
INLINE_CAP = 6_000_000


def _inject_csp(html: str) -> str:
    """A structural backstop for the regex stripping above: regex is not an HTML parser and
    can't be made airtight against it (KTD: this whole module's docstring calls the result
    "inert", which only a real enforcement mechanism can back up). This CSP blocks every
    script and frame outright in the offline render, whatever slipped through. style-src
    'unsafe-inline' and img-src/font-src data: allow the CSS and assets vendor_html already
    inlined -- nothing here needs a live network request, which was already blocked anyway."""
    m = _HEAD_OPEN.search(html)
    if m:
        return html[:m.end()] + _CSP_META + html[m.end():]
    m = _HTML_OPEN.search(html)
    if m:
        return html[:m.end()] + f"<head>{_CSP_META}</head>" + html[m.end():]
    return _CSP_META + html


def _attr(tag: str, name: str) -> str | None:
    m = _ATTR(name).search(tag)
    return m.group(1).strip("\"'") if m else None


def _strip_active(html: str) -> str:
    # Regex is not an HTML parser, and each of these was a real bypass: a closing tag can
    # carry its own bogus attributes ("</script foo>" still closes the tag to a browser), and
    # an unpaired opening tag with no matching close (a bare "<iframe src=...>") survives a
    # pattern that only strips matched pairs. This is inherently incomplete -- see the CSP
    # injected in vendor_html below for the structural backstop.
    for pat in (r"<script\b.*?</script[^>]*>", r"<script\b[^>]*>",
                r"<iframe\b.*?</iframe[^>]*>", r"<iframe\b[^>]*>",
                r"<object\b.*?</object[^>]*>", r"<embed\b[^>]*>", r"<base\b[^>]*>",
                r"<meta\b[^>]*http-equiv\s*=\s*[\"']?refresh[^>]*>"):
        html = re.sub(pat, "", html, flags=re.I | re.S)
    # A "/" before an attribute name (e.g. "<svg/onload=...>") is whitespace to an HTML
    # tokenizer, not just a self-close marker -- a known real-world bypass of "\son\w+".
    html = re.sub(r"[\s/]on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
    html = re.sub(r"(href|src|action)\s*=\s*([\"'])\s*javascript:[^\"']*\2", r'\1=\2#\2', html, flags=re.I)
    html = re.sub(r"(<textarea\b[^>]*>).*?(</textarea\s*>)", r"\1\2", html, flags=re.I | re.S)

    def blank_input(m):
        tag = m.group(0)
        kind = (_attr(tag, "type") or "text").lower()
        if kind in ("submit", "button", "reset", "image", "checkbox", "radio"):
            return tag
        return re.sub(r"\svalue\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", tag, flags=re.I)

    return re.sub(r"<input\b[^>]*>", blank_input, html, flags=re.I)


def _memoized(fetch):
    """Fetch each URL once: a repeat gets the same bytes, or raises the same error again."""
    seen: dict = {}

    def get(url: str) -> bytes:
        if url not in seen:
            try:
                seen[url] = (fetch(url), None)
            except Exception as e:
                seen[url] = (None, e)
        data, err = seen[url]
        if err is not None:
            raise err
        return data

    return get


def _inline_css(css: str, base: str, fetch, fetch_asset, budget: list, notes: list, depth: int = 0) -> str:
    def imp(m):
        target = m.group(2) or m.group(4)
        if depth >= 2 or not target or target.startswith("data:"):
            return ""
        url = urljoin(base, target)
        try:
            sub = fetch(url).decode("utf-8", "replace")
        except Exception as e:
            # A silently dropped @import can drop a visibility-hiding rule with it (KTD:
            # structural PASS must not trust a snapshot with rules missing), so this has to
            # surface as a note the caller turns into ok=False, not just an empty substitution.
            notes.append(f"@import not fetched: {url} ({e})")
            return ""
        return _inline_css(sub, url, fetch, fetch_asset, budget, notes, depth + 1)

    css = _IMPORT.sub(imp, css)

    def asset(m):
        target = m.group(2).strip()
        if not target or target.startswith(("data:", "#")):
            return m.group(0)
        try:
            data = fetch_asset(urljoin(base, target))
        except Exception:
            return 'url("")'
        budget[0] += len(data)
        if budget[0] > INLINE_CAP:
            return 'url("")'
        mime = mimetypes.guess_type(target.split("?")[0])[0] or "application/octet-stream"
        return f'url("data:{mime};base64,{base64.b64encode(data).decode()}")'

    return _URL.sub(asset, css)


def vendor_html(html: str, fetch, base_url: str = "", fetch_asset=None) -> tuple[str, bool, list[str]]:
    fetch_asset = _memoized(fetch_asset or fetch)
    fetch = _memoized(fetch)
    notes: list[str] = []
    ok = True
    budget = [0]
    html = _strip_active(html)

    # An inline <style> block's @import is never resolved by this pass (only <link> sheets
    # are), and the offline render blocks all network requests -- so its rules, possibly
    # including a visibility-hiding one, silently never apply. That must not read as ok=True.
    for content in _STYLE_BLOCK.findall(html):
        if "@import" in content:
            notes.append("an inline <style> block contains @import, which this vendoring pass "
                         "does not resolve; its rules will not apply in the offline render")
            ok = False
            break

    def link(m):
        nonlocal ok
        tag = m.group(0)
        if "stylesheet" not in (_attr(tag, "rel") or "").lower():
            return tag
        href = _attr(tag, "href")
        if not href:
            return ""
        url = urljoin(base_url, href)
        try:
            css = fetch(url).decode("utf-8", "replace")
        except Exception as e:
            notes.append(f"stylesheet not fetched: {url} ({e})")
            ok = False
            return ""
        before = len(notes)
        css = _inline_css(css, url, fetch, fetch_asset, budget, notes)
        # Case-sensitive escaping let "</STYLE><script>...">" close the tag early and inject
        # a live script into the offline render, which trusts this snapshot's DOM and
        # screenshot for verdicts -- fetched CSS is attacker-controlled (any host that passes
        # the fetch policy), so this has to be airtight, not just cover the common case.
        css = re.sub(r"</(style)", r"<\\/\1", css, flags=re.I)
        css = css.replace("<!--", "<\\!--")
        if len(notes) > before:
            ok = False
        return f'<style data-vendored-from="{href}">{css}</style>'

    return _inject_csp(_LINK.sub(link, html)), ok, notes
