#!/usr/bin/env python3
"""Build the seeded 'agency rebuild' fixture from the pristine live capture.

The baseline is the faithful one, extracted from the page (baseline-from-capture.py), so every
defect lives on the *page*, where the fault lies: the agency altered approved copy or broke
the page's structure.

Two kinds, because they exercise different reviewer capabilities:

  P4-P6  copy the agency changed. A verbatim comparison catches these.
  P1-P3  structure the agency broke. P2 in particular is invisible to text extraction — the
         disclaimer's text is unchanged, only its visibility is — so it needs the
         on_load_visible flag (CLAUDE.md §3).

Order matters: P6 edits the disclaimer's text, and P2 then wraps that edited paragraph.

Usage:
    python3 fixtures/seed-defects.py
"""

import pathlib
import sys

SRC = pathlib.Path(__file__).parent / "live-2026-09-20.html"
DST = pathlib.Path(__file__).parent / "agency-rebuild-2026-09-20.html"

DISC_STYLE = '<p style="color:#888;font-size:10px;font-style:italic;line-height:normal">'
DISC_OLD = (
    "*The Manufacturer’s Suggested Retail Price excludes destination freight charge, "
    "tax, title, license, dealer fees and optional equipment. Dealer sets final price."
)
DISC_NEW = (  # P6: "dealer fees" omitted from the exclusions
    "*The Manufacturer’s Suggested Retail Price excludes destination freight charge, "
    "tax, title, license and optional equipment. Dealer sets final price."
)

# (label, find, replace) — each `find` must match the capture exactly once.
DEFECTS = [
    (
        "P4 CT5-V starting MSRP altered: $57,600 -> $58,900",
        '<td class="text-center">$57,600</td>',
        '<td class="text-center">$58,900</td>',
    ),
    (
        "P5 intro claim altered: 'nearly two decades' -> 'over two decades'",
        "Born and bred on the track, nearly two decades of relentless engineering",
        "Born and bred on the track, over two decades of relentless engineering",
    ),
    (
        "P6 disclaimer exclusion omitted: 'dealer fees'",
        DISC_STYLE + DISC_OLD + "</p>",
        DISC_STYLE + DISC_NEW + "</p>",
    ),
    (
        "P1 asterisk dropped from Starting MSRP label",
        "<strong>Starting MSRP*</strong>",
        "<strong>Starting MSRP</strong>",
    ),
    (
        "P2 MSRP disclaimer moved behind a read-more toggle",
        DISC_STYLE + DISC_NEW + "</p>",
        '<details><summary style="color:#888;font-size:10px;cursor:pointer">Read more</summary>'
        + DISC_STYLE + DISC_NEW + "</p></details>",
    ),
    (
        "P3 illustrative finish list presented as exhaustive",
        "available in finishes that include polished silver",
        "available in three finishes: polished silver",
    ),
]


def main() -> int:
    html = SRC.read_text(encoding="utf-8")

    for label, find, replace in DEFECTS:
        count = html.count(find)
        if count != 1:
            print(f"ABORT: {label!r} matched {count} times, expected exactly 1")
            return 1
        html = html.replace(find, replace)
        print(f"seeded: {label}")

    DST.write_text(html, encoding="utf-8")
    print(f"\nwrote {DST.name} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
