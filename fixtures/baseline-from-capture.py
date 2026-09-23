#!/usr/bin/env python3
"""Generate a faithful ground-truth baseline directly from a page capture.

Every boxed quote in the output is read from the captured DOM, not retyped, so the baseline
cannot contain a transcription error. The result is the *faithful* baseline: the same capture
passes every copy check against it (zero FAIL). It is not all-PASS — it records the tab title
and the H1 verbatim, and they disagree with each other, so a correct reviewer still returns
`OPEN — PAGE INCONSISTENT` for the model year (see ANSWER-KEY.md, Run A). Because it is
faithful, defects can only live on the page — see seed-defects.py.

This script *is* the source of the committed GROUND-TRUTH_ct5v-vs-ct5v-blackwing.md: regenerating
from fixtures/live-2026-09-20-recapture.html reproduces it byte for byte. Its layout follows an
earlier hand-edited baseline (v1.x, in git history). One thing is not extractable and is
carried over as-is: the disclaimer's five mandatory conditions, which are pass/fail rules, not
page copy. (Condition 3's exclusion list is derived from the extracted disclaimer.)

On 2026-09-20 the PMM's Word pass removed two things this script used to emit: the
`Source capture` header line and the Premium Options table. The generator now matches that
edited doc, so regenerating still reproduces the committed file. The capture's sha256 is printed
to stdout instead of written into the doc.

The script aborts if the page's block structure is not the one it expects, so a redesigned
page fails loudly instead of producing a plausible-looking wrong baseline.

Usage:
    python3 fixtures/baseline-from-capture.py <capture.html> <output.md> [capture-date]
"""

import hashlib
import html
import pathlib
import re
import sys
from html.parser import HTMLParser

URL = "https://www.crestmontcadillac.com/ct5v-vs-ct5v-blackwing-comparison/"


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


class Main(HTMLParser):
    """Collect the ordered content blocks of <main>."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.in_main = False
        self.blocks = []        # (kind, payload)
        self._cap = None        # (kind, [text])
        self._row = None
        self._table = None

    def _open(self, kind):
        self._cap = (kind, [])

    def _close(self):
        kind, parts = self._cap
        self._cap = None
        text = clean("".join(parts))
        if kind in ("th", "td"):
            self._row.append(text)
        elif text:
            self.blocks.append((kind, text))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "main":
            self.in_main = True
        if not self.in_main:
            return
        if tag in ("h1", "h2", "p"):
            self._open(tag)
        elif tag == "a" and "btn" in (a.get("class") or ""):
            self._open("cta")
        elif tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._open(tag)

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False
        if not self.in_main:
            return
        if tag in ("h1", "h2", "p", "a") and self._cap and (
            self._cap[0] == tag or (tag == "a" and self._cap[0] == "cta")
        ):
            self._close()
        elif tag in ("th", "td") and self._cap:
            self._close()
        elif tag == "tr":
            self._table.append(self._row)
            self._row = None
        elif tag == "table":
            self.blocks.append(("table", self._table))
            self._table = None

    def handle_data(self, data):
        if self._cap:
            self._cap[1].append(data)

    def handle_entityref(self, name):
        if self._cap:
            self._cap[1].append(f"&{name};")

    def handle_charref(self, name):
        if self._cap:
            self._cap[1].append(f"&#{name};")


def extract(raw: str) -> dict:
    title = clean(re.search(r"<title[^>]*>(.*?)</title>", raw, re.S).group(1))

    crumbs = re.search(r'<span id="breadcrumbs">(.*?)</div>', raw, re.S).group(1)
    crumbs = clean(re.sub(r"<[^>]+>", " ", crumbs))
    crumbs = re.sub(r"^You are here:\s*", "", crumbs)
    crumbs = re.sub(r"\s+»\s+", " » ", crumbs)

    p = Main()
    p.feed(raw)
    shape = [k for k, _ in p.blocks]
    expected = [
        "h1", "p", "cta", "cta", "h2", "table", "p", "p",
        "h2", "p", "h2", "p", "cta", "cta", "p",
    ]
    if shape != expected:
        sys.exit(
            "ABORT: the page's content blocks are not the expected shape.\n"
            f"  expected: {expected}\n  found:    {shape}\n"
            "The page was redesigned or the capture is wrong; update this script deliberately."
        )
    b = [v for _, v in p.blocks]
    if [b[2], b[3]] != [b[12], b[13]]:
        sys.exit("ABORT: the two CTA pairs are not identical; the baseline asserts they are.")

    return {
        "title": title, "breadcrumb": crumbs, "h1": b[0], "intro": b[1],
        "cta_primary": b[2], "cta_secondary": b[3], "spec_heading": b[4],
        "table": b[5], "narr_v": b[6], "narr_bw": b[7], "ext_heading": b[8],
        "ext": b[9], "int_heading": b[10], "int": b[11], "disclaimer": b[14],
    }


def exclusions(disclaimer: str) -> list[str]:
    m = re.search(r"excludes (.*?)\. Dealer sets final price", disclaimer)
    parts = re.split(r",\s*|\s+and\s+", m.group(1))
    return [x for x in parts if x]


def render(d: dict, date: str) -> str:
    t = d["table"]
    header, rows = t[0], t[1:]
    assert len(header) == 3 and all(len(r) == 3 for r in rows), "unexpected table shape"
    if len(rows) != 7:
        sys.exit(f"ABORT: expected 7 spec rows, found {len(rows)}")
    table = "\n".join(f"| {a} | {b} | {c} |" for a, b, c in rows)
    excl = exclusions(d["disclaimer"])
    words = {6: "six", 7: "seven"}[len(excl)]
    sep = "&nbsp;&nbsp;|&nbsp;&nbsp;"

    return f"""# Ground Truth — Approved Page Copy

## {d['h1']}

**Page URL:** {URL}
**Captured:** {date}
**Owner:** Product Marketing
**Status:** Draft

**Scope:** Approved **copy only** — headings, body copy, specification values, option and
package claims, CTA labels and disclaimers within the main content column.

**Out of scope:** Global navigation, dealership contact details, footer link lists, social
icons, site-vendor credits, images, layout, page elements and animations.

Copy shown in a boxed quote must match **character for character**, including
capitalization, punctuation, hyphenation and units. Anything outside a boxed quote is
guidance, not approved copy.

---

## Page Identity

**Browser tab title (SEO title)**

> {d['title']}

**Page headline (H1)**

> {d['h1']}

**Breadcrumb trail**

> {d['breadcrumb']}

---

## Introduction

**Opening description paragraph**

> {d['intro']}

---

## Call-to-Action Labels

**Primary CTA label**

> {d['cta_primary']}

**Secondary CTA label**

> {d['cta_secondary']}

---

## Vehicle Details — Performance Specifications

**Section heading**

> {d['spec_heading']}

**Comparison table column headers**

Left column header, center divider, right column header:

> {header[0]} {sep} {header[1]} {sep} {header[2]}

**Specification rows**

The page presents each row as: *CT5-V value — row label — Blackwing value.*

| {header[0]} | Spec label | {header[2]} |
| --- | --- | --- |
{table}

---

## Performance Narrative Copy

**CT5-V paragraph**

> {d['narr_v']}

**CT5-V Blackwing paragraph**

> {d['narr_bw']}

---

## Key Features — Exterior

**Section heading**

> {d['ext_heading']}

**Body copy**

> {d['ext']}

---

## Key Features — Interior

**Section heading**

> {d['int_heading']}

**Body copy**

> {d['int']}

---

## Disclaimer Copy

**MSRP disclaimer**

**Anchor:** Bound to the asterisk in the `Starting MSRP*` row label.
**Placement:** End of the main content column, following the second CTA pair.

> {d['disclaimer']}

**Mandatory conditions — each is independently a pass/fail:**

1. The disclaimer is present whenever **any** price appears on the page.
2. The leading asterisk is present and matches the asterisk on the `Starting MSRP*` label.
3. All {words} exclusions appear, in this order: {', '.join(excl)}.
4. The closing sentence "Dealer sets final price." is present and unabbreviated.
5. The disclaimer is rendered as visible text on page load — not hidden behind a tooltip, accordion, modal or "read more" toggle.
"""


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        return 2
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    date = sys.argv[3] if len(sys.argv) == 4 else "2026-09-20"
    raw = src.read_text(encoding="utf-8")
    d = extract(raw)
    md = render(d, date)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out} — {md.count(chr(10)):,} lines, "
          f"{len(exclusions(d['disclaimer']))} disclaimer exclusions")
    print(f"source: {src.name}  sha256 {hashlib.sha256(raw.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
