"""Deterministic checks: verbatim matching and structural (visibility) conditions.

The model never decides these (KTD8). A verbatim item passes on an exact match, after
typographic normalization, to a whole page block or to a whole-token span inside one block.
A near match fails and carries the page text plus a word-level diff; below the similarity
floor the item is NOT FOUND ON PAGE.
"""

from __future__ import annotations

import difflib
import hashlib

from .schema import ChecklistItem, Finding, PageBlock
from .typography import normalize as _n

FLOOR = 0.6
_VISIBILITY_TIER = {"visible": 0, "undetermined": 1, "hidden": 2}


def evidence_hash(cited: list[str]) -> str:
    return hashlib.sha1("\n".join(cited).encode("utf-8")).hexdigest()[:12]


def diff_excerpt(approved: str, page: str) -> str:
    a, b = approved.split(), page.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        old, new = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if op == "replace":
            out.append(f'approved "{old}" but page has "{new}"')
        elif op == "delete":
            out.append(f'page is missing "{old}"')
        else:
            out.append(f'page adds "{new}"')
        if len(out) == 4:
            break
    return "; ".join(out) if out else "text differs"


_GLUE = set("*†‡%")   # footnote/qualifier marks: an added one must not be waved through


def _glued(hay: str, at: int, step: int) -> bool:
    """True if the character at `hay[at]` (stepping outward by `step`) glues onto a match: a
    footnote mark, or punctuation that continues into a digit (a dropped/added decimal, e.g.
    "$57,600" matching inside "$57,600.99"). An out-of-range index is a string boundary, never
    glued -- unlike the empty string `""`, which `in`/`.isalnum()` checks can't distinguish from
    "no glue" by accident."""
    if not (0 <= at < len(hay)):
        return False
    ch = hay[at]
    if ch in _GLUE or ch.isalnum():
        return True
    if ch in ".,-" and 0 <= at + step < len(hay) and hay[at + step].isdigit():
        return True
    return False


def _span(needle: str, hay: str) -> bool:
    start = 0
    while (i := hay.find(needle, start)) != -1:
        end = i + len(needle)
        if not _glued(hay, i - 1, -1) and not _glued(hay, end, 1):
            return True
        start = i + 1
    return False


def _finding(item, verdict, blocks_used, explanation="", check_by_eye=False, cited=None) -> Finding:
    cited = cited if cited is not None else [_n(b.text) for b in blocks_used]
    return Finding(
        item_id=item.id, verdict=verdict, approved_text=item.text,
        quote=" | ".join(b.text for b in blocks_used), block=blocks_used[0].index if blocks_used else None,
        cited=cited, evidence_hash=evidence_hash(cited) if cited else "",
        explanation=explanation, check_by_eye=check_by_eye)


def similarity(a: str, b: str, beat: float = 0.0) -> float:
    """Text similarity in [0, 1]; 0.0 when it cannot reach the floor or cannot beat `beat`."""
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if m.real_quick_ratio() < FLOOR or m.quick_ratio() < FLOOR or m.quick_ratio() <= beat:
        return 0.0
    return m.ratio()


def check_verbatim(item: ChecklistItem, blocks: list[PageBlock], occurrence: int) -> Finding:
    need = _n(item.text)

    if item.locator:
        cell = [b for b in blocks if b.table == item.locator]
        if not cell:
            return _finding(item, "NOT FOUND ON PAGE", [],
                            "no page table cell at the approved location")
        located = cell[0]
        if _n(located.text) == need:
            return _finding(item, "PASS", [located])
        # the cell at this exact (table, row, col) differs; before failing, check the same
        # row/col under a different table index -- the page's table count (every <table> in
        # the DOM) and the baseline's (approved-doc tables only) can legitimately disagree
        # when an unrelated table sits earlier on the page, shifting every index after it
        shifted = [b for b in blocks
                  if b is not located and b.table
                  and b.table["row"] == item.locator["row"] and b.table["col"] == item.locator["col"]
                  and _n(b.text) == need]
        if shifted:
            return _finding(item, "WARN", [shifted[0]],
                            "found at the same row/column but a different table index than the "
                            "approved baseline; the page's table order may have shifted",
                            check_by_eye=True)
        return _finding(item, "FAIL", [located], diff_excerpt(need, _n(located.text)))

    # Among several matches, a visible one should be cited before a hidden or undetermined
    # one: a hidden print-only/aria-hidden duplicate must not get cited over a real visible
    # copy, which would fail an otherwise-correct disclaimer's structural (visible-on-load)
    # condition. Occurrence indexing still applies within each visibility tier -- the sort
    # is stable, so relative page order among equally-visible blocks is unchanged.
    whole = sorted((b for b in blocks if _n(b.text) == need), key=lambda b: _VISIBILITY_TIER[b.visible])
    span_only = [] if whole else [b for b in blocks if _span(need, _n(b.text))]
    hits = whole or span_only
    if hits:
        if occurrence < len(hits):
            hit = hits[occurrence]
            if not whole:
                if hit.kind == "title":
                    return _finding(item, "WARN", [hit],
                                    "the approved copy is found only as a fragment inside the page "
                                    "title, not as its own block", check_by_eye=True)
                if hit.visible == "hidden":
                    return _finding(item, "WARN", [hit],
                                    "the approved copy is found only as a fragment inside a hidden "
                                    "block", check_by_eye=True)
            return _finding(item, "PASS", [hit])
        return _finding(item, "NOT FOUND ON PAGE", [],
                        f"the approved copy appears {occurrence + 1} times, the page has {len(hits)}")

    if "|" in need:                       # a header quote: match the cells of one page table row
        cells = [c.strip() for c in need.split("|")]
        rows: dict[tuple, list[PageBlock]] = {}
        for b in blocks:
            if b.table:
                rows.setdefault((b.table["table"], b.table["row"]), []).append(b)
        best, best_score = None, 0.0
        for row in rows.values():
            row.sort(key=lambda b: b.table["col"])
            if len(row) != len(cells):
                continue
            score = sum(similarity(c, _n(b.text)) for c, b in zip(cells, row)) / len(cells)
            if score > best_score:
                best, best_score = row, score
        if best and best_score >= FLOOR:
            page = " | ".join(_n(b.text) for b in best)
            if page == " | ".join(cells):
                return _finding(item, "PASS", best)
            return _finding(item, "FAIL", best, diff_excerpt(" | ".join(cells), page))

    best, best_score = None, 0.0
    for b in blocks:
        t = _n(b.text)
        if not t or not (0.4 * len(need) <= len(t) <= 2.5 * len(need)):
            continue
        score = similarity(need, t, beat=best_score)
        if score > best_score:
            best, best_score = b, score
    if best is not None and best_score >= FLOOR:
        return _finding(item, "FAIL", [best], diff_excerpt(need, _n(best.text)))
    return _finding(item, "NOT FOUND ON PAGE", [], "no page block resembles the approved copy")


def check_structural(item: ChecklistItem, results: dict, blocks: list[PageBlock]) -> Finding:
    by_index = {b.index: b for b in blocks}
    if not item.subjects:
        return _finding(item, "NOT FOUND ON PAGE", [], "the condition names no subject items")
    used = []
    for s in item.subjects:
        r = results.get(s)
        if r is None or r.block is None or r.block not in by_index:
            return _finding(item, "NOT FOUND ON PAGE", [], f"subject item {s} was not found on the page")
        used.append(by_index[r.block])
    states = {b.visible for b in used}
    cited = [f"{_n(b.text)} [{b.visible}]" for b in used]      # visibility is part of the evidence
    if "hidden" in states:
        return _finding(item, "FAIL", used, "the text is present but not visible on page load", cited=cited)
    if "undetermined" in states:
        return _finding(item, "WARN", used, "visibility could not be determined; check by eye",
                        check_by_eye=True, cited=cited)
    return _finding(item, "PASS", used, cited=cited)
