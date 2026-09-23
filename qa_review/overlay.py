"""The annotated page (R18, R19): the real rendered page, marked up, and a clickable report.

Outlines and badges are placed over the recorded boxes of the real snapshot, so nothing on the
overlay is generated text. Badge numbers are the ones stored on the record (U7). The snapshot
is re-rendered with every network request blocked, exactly as at capture. The HTML report is
one self-contained file: the screenshot embedded as an image, every string escaped, a content
security policy that allows only its own inline script.
"""

from __future__ import annotations

import base64
import hashlib
import html as htmllib
import pathlib

from .capture import offline_page
from .render import NOT_ON_PAGE_TEXT, excerpt_pair, short_verdict
from .schema import FindingsRecord, PageBlock

COLORS = {"FAIL": "#c62828", "WARN": "#ef6c00", "CHECK": "#6a1b9a", "OPEN": "#1565c0", "NOT FOUND": "#616161"}

INJECT = """(items) => {
  for (const it of items) {
    const [x, y, w, h] = it.box;
    const o = document.createElement('div');
    o.style.cssText = `position:absolute;left:${x - 3}px;top:${y - 3}px;width:${w + 6}px;height:${h + 6}px;` +
      `outline:3px solid ${it.color};background:${it.color}22;z-index:2147483646;pointer-events:none`;
    const b = document.createElement('span');
    b.textContent = `${it.number} ${it.label}`;
    b.style.cssText = `position:absolute;left:0;top:${-24 - 24 * it.stack}px;background:${it.color};color:#fff;` +
      `font:bold 13px sans-serif;padding:2px 6px;border-radius:3px;white-space:nowrap`;
    o.appendChild(b);
    document.body.appendChild(o);
  }
}"""

SCRIPT = (
    "document.querySelectorAll('#list li[data-y]').forEach(function (li) {"
    "li.addEventListener('click', function () {"
    "document.getElementById('shot').scrollTo({top: Math.max(0, Number(li.dataset.y) - 120), behavior: 'smooth'});"
    "});});"
)


def _label(f) -> str:
    if f.check_by_eye:
        return "CHECK"
    if f.verdict.startswith("OPEN"):
        return "OPEN"
    return short_verdict(f)


def _box(b: PageBlock | None):
    if b is None:
        return None
    if b.visible == "hidden":
        return b.anchor_bbox
    return b.bbox


def _entries(record: FindingsRecord, blocks: list[PageBlock]) -> list[dict]:
    by = {b.index: b for b in blocks}
    out = []
    for f in sorted((f for f in record.findings if f.number is not None), key=lambda f: f.number):
        label = _label(f)
        out.append({"number": f.number, "item_id": f.item_id, "label": label, "color": COLORS[label],
                    "box": _box(by.get(f.block)),
                    "quote": f.quote, "approved": f.approved_text, "explanation": f.explanation})
    seen: dict[tuple, int] = {}
    for e in out:
        if e["box"]:
            key = tuple(round(v) for v in e["box"])
            e["stack"] = seen.get(key, 0)
            seen[key] = e["stack"] + 1
    return out


def _render(snapshot: pathlib.Path, placed: list[dict]):
    with offline_page(snapshot) as page:
        page.evaluate(INJECT, [{k: e[k] for k in ("number", "label", "color", "box", "stack")} for e in placed])
        return page.screenshot(full_page=True)


def _report_html(record: FindingsRecord, entries: list[dict], png: bytes | None, degraded: bool) -> str:
    e = htmllib.escape
    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'"
    rows = []
    for it in entries:
        page_x, approved_x = excerpt_pair(it["quote"], it["approved"])
        located = it["box"] is not None and not degraded
        attrs = f' data-y="{round(it["box"][1])}" tabindex="0"' if located else ""
        note = "" if located else " <em>(no location on the page)</em>"
        rows.append(
            f'<li{attrs}><span class="tag" style="background:{it["color"]}">{it["number"]} {e(it["label"])}</span> '
            f'<code>{e(it["item_id"])}</code>{note}<br>Page: &ldquo;{e(page_x or NOT_ON_PAGE_TEXT)}&rdquo;'
            f'<br>Approved copy: &ldquo;{e(approved_x)}&rdquo;'
            + (f'<br>{e(it["explanation"])}' if it["explanation"] else "") + "</li>")
    shot = ('<p class="notice">This page\'s styles were not vendored, so no annotated screenshot was produced.</p>'
            if degraded or png is None else
            f'<div id="shot"><img alt="Annotated page" src="data:image/png;base64,{base64.b64encode(png).decode()}"></div>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>Review report</title>
<style>
body{{font:15px/1.5 -apple-system,Segoe UI,sans-serif;margin:0;color:#1b1f24}}
header{{padding:12px 20px;border-bottom:1px solid #ddd}}
.layout{{display:flex;gap:16px;padding:12px 20px;align-items:flex-start}}
#list{{width:34%;padding-left:20px;max-height:85vh;overflow:auto}} #list li{{margin:0 0 12px;cursor:pointer}}
#shot{{flex:1;max-height:85vh;overflow:auto;border:1px solid #ddd}} #shot img{{display:block;max-width:none}}
.tag{{color:#fff;font-weight:bold;padding:1px 6px;border-radius:3px;font-size:12px}}
.notice{{padding:12px 20px}}
</style></head><body>
<header><h1>Review &mdash; {e(record.baseline["slug"])} against {e(record.page["key"])}</h1></header>
<div class="layout"><ol id="list">{"".join(rows) or "<li>No findings to show.</li>"}</ol>{shot}</div>
<script>{SCRIPT}</script>
</body></html>
"""


def build_overlay(record: FindingsRecord, blocks: list[PageBlock], snapshot, out_dir) -> dict:
    out_dir = pathlib.Path(out_dir)
    degraded = not record.page.get("styles_vendored", False)
    entries = _entries(record, blocks)
    placed = [] if degraded else [e for e in entries if e["box"]]
    png = None
    png_path = None
    if not degraded:
        png = _render(pathlib.Path(snapshot), placed)
        png_path = out_dir / "annotated.png"
        png_path.write_bytes(png)
    html_path = out_dir / "report.html"
    html_path.write_text(_report_html(record, entries, png, degraded), encoding="utf-8")
    return {"placed": placed, "png": png_path, "html": html_path}
