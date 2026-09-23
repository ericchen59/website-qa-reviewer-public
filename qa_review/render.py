"""Reading surfaces, rendered from the findings record and nothing else (R12, R15-R17).

report.md: the coverage line, the failures-first table, the lists for Marketing and for a
look by eye, the round diff and the footnotes. agency-block.md: plain text she can paste.
Every page- or model-derived string is escaped (report) or neutralized (agency block).
"""

from __future__ import annotations

import difflib
import re

from .diff import RoundDiff
from .schema import Finding, FindingsRecord

ORDER = {"FAIL": 0, "NOT FOUND ON PAGE": 1, "WARN": 2}
DAGGER = "†"
_MD_SPECIAL = re.compile(r"([\\`*_\[\]()<>|#~])")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def is_agency(f: Finding) -> bool:
    return f.verdict in ORDER and not f.check_by_eye


def is_open(f: Finding) -> bool:
    return f.verdict.startswith("OPEN")


def assign_numbers(record: FindingsRecord) -> None:
    """One sequence shared by the report lists and the annotated page: table rows first,
    then the Marketing list, then Check by eye."""
    position = {f.item_id: i for i, f in enumerate(record.findings)}
    agency = sorted((f for f in record.findings if is_agency(f)),
                    key=lambda f: (ORDER[f.verdict], position[f.item_id]))
    opens = [f for f in record.findings if is_open(f)]
    eye = [f for f in record.findings if f.check_by_eye]
    for n, f in enumerate(agency + opens + eye, start=1):
        f.number = n


def esc(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", _CTRL.sub("", " ".join(str(text).split())))


def plain(text: str) -> str:
    """For text pasted into email: drop control characters, neutralize link syntax."""
    return _CTRL.sub("", str(text)).replace("](", "] (")


LIMIT = 220
CONTEXT = 8
MAX_SPAN = 40


def excerpt_pair(page: str, approved: str, limit: int = LIMIT) -> tuple[str, str]:
    """Long texts are cut to the changed words plus context, so a table row stays scannable.
    The full text stays in findings.json."""
    if max(len(page), len(approved)) <= limit:
        return page, approved

    def head(t):
        return t if len(t) <= limit else t[:limit].rstrip() + "\u2026"

    if not page or not approved:
        return head(page), head(approved)
    a, b = approved.split(), page.split()
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    if not ops:
        return head(page), head(approved)
    first = ops[0]
    span = [o for o in ops if o[1] - first[1] <= MAX_SPAN and o[3] - first[3] <= MAX_SPAN]
    i1, i2, j1, j2 = first[1], span[-1][2], first[3], span[-1][4]

    def cut(words, lo, hi):
        lo2, hi2 = max(0, lo - CONTEXT), min(len(words), hi + CONTEXT)
        return ("\u2026 " if lo2 > 0 else "") + " ".join(words[lo2:hi2]) + (" \u2026" if hi2 < len(words) else "")

    return cut(b, j1, j2), cut(a, i1, i2)


NOT_ON_PAGE_TEXT = "(not found on the page)"


def short_verdict(f: Finding) -> str:
    return "NOT FOUND" if f.verdict == "NOT FOUND ON PAGE" else f.verdict


def _pair(f: Finding) -> tuple[str, str]:
    page, approved = excerpt_pair(f.quote, f.approved_text)
    return (page if page else NOT_ON_PAGE_TEXT), approved


def coverage_line(record: FindingsRecord) -> str:
    c = record.counts()
    total = len(record.findings)
    opens = c["OPEN — NEEDS MARKETING"] + c["OPEN — PAGE INCONSISTENT"]
    if c["PASS"] + c["FAIL"] + c["WARN"] + c["NOT FOUND ON PAGE"] + opens != total:
        raise ValueError("coverage counts do not sum to the total")
    return (f"{total}/{total} checked: {c['PASS']} PASS, {c['FAIL']} FAIL, {c['WARN']} WARN, "
            f"{c['NOT FOUND ON PAGE']} NOT FOUND, {opens} OPEN")


def render_report(record: FindingsRecord, diff: RoundDiff | None) -> str:
    marks = {p.new_id for p in diff.pairs} if diff else set()
    lines = [f"# Review — {esc(record.baseline['slug'])} against {esc(record.page['key'])}", "",
             f"**{coverage_line(record)}**", "",
             f"Run {record.run_id} · baseline `{record.baseline['hash'][:8]}`"
             + ("" if record.page.get("styles_vendored") else " · page styles were not vendored (visibility and overlay degraded)"),
             ""]
    if record.typography_rules:
        lines += [f"_Typography was normalized before comparing: {', '.join(record.typography_rules)}._", ""]

    table = sorted((f for f in record.findings if is_agency(f)), key=lambda f: f.number or 0)
    lines += ["## Findings for the agency", ""]
    if table:
        lines += ["| # | ID | Severity | Page says | Approved copy says |", "| --- | --- | --- | --- | --- |"]
        for f in table:
            page, approved = _pair(f)
            lines.append(f"| {f.number} | {f.item_id}{DAGGER if f.item_id in marks else ''} | {short_verdict(f)} | "
                         f"{esc(page)} | {esc(approved)} |")
        detail = [f for f in table if f.explanation]
        if detail:
            lines += ["", "Details:"] + [f"- #{f.number}: {esc(f.explanation)}" for f in detail]
    else:
        lines.append("No failures, warnings or missing copy.")
    lines.append("")

    opens = sorted((f for f in record.findings if is_open(f)), key=lambda f: f.number or 0)
    if opens:
        lines += ["## Open items for Marketing", ""]
        for f in opens:
            page, approved = _pair(f)
            lines.append(f"{f.number}. `{f.item_id}`{DAGGER if f.item_id in marks else ''} — {f.verdict}. "
                         f"Page: “{esc(page)}”. Approved copy: “{esc(approved)}”. "
                         f"{esc(f.explanation)}".rstrip())
        lines.append("")
    eye = sorted((f for f in record.findings if f.check_by_eye), key=lambda f: f.number or 0)
    if eye:
        lines += ["## Check by eye", ""]
        for f in eye:
            page, approved = _pair(f)
            lines.append(f"{f.number}. `{f.item_id}` — {esc(approved)} (page: “{esc(page)}”). "
                         f"{esc(f.explanation)}".rstrip())
        lines.append("")

    if diff is not None:
        lines += ["## Since the last round", ""]
        for e in diff.entries:
            mark = DAGGER if e.item_id in marks else ""
            if e.category == "replaces":
                lines.append(f"- `{e.item_id}`{mark} replaces `{e.replaces}` — now {e.verdict}")
            elif e.category == "verdict changed, page unchanged":
                lines.append(f"- Verdict changed, page unchanged: review — `{e.item_id}` (was {e.prior_verdict}, now {e.verdict})")
            elif e.category in ("regressed", "fixed"):
                lines.append(f"- {e.category.capitalize()} — `{e.item_id}` ({e.prior_verdict} → {e.verdict})")
            elif e.category == "new":
                lines.append(f"- New — `{e.item_id}` ({e.verdict})")
            else:
                lines.append(f"- Still open — `{e.item_id}` ({e.verdict})")
        lines += [f"- {diff.unchanged} items unchanged and passing.", ""]
        if diff.pairs or diff.removed:
            lines += ["## Footnotes", ""]
            for p in diff.pairs:
                lines.append(f"{DAGGER} `{p.new_id}` replaces `{p.old_id}`. Approved copy was: "
                             f"“{esc(p.old_text)}”; now: “{esc(p.new_text)}”.")
            for r in diff.removed:
                lines.append(f"Removed from approved copy: `{r.item_id}` — “{esc(r.text)}”.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_agency_block(record: FindingsRecord) -> str:
    rows = sorted((f for f in record.findings if is_agency(f)), key=lambda f: f.number or 0)
    head = f"The review of {plain(record.page['key'])} against the approved copy"
    if not rows:
        eye = sum(1 for f in record.findings if f.check_by_eye)
        opens = sum(1 for f in record.findings if is_open(f))
        if eye or opens:
            # Findings the agency isn't cleared of yet -- an unresolved review must not read
            # as an affirmative "no differences" when there's still something to look at.
            parts = []
            if eye:
                parts.append(f"{eye} item{'s' if eye != 1 else ''} still need{'s' if eye == 1 else ''} "
                             "a look (check by eye)")
            if opens:
                parts.append(f"{opens} open item{'s' if opens != 1 else ''} for Marketing")
            return head + f" found no confirmed differences, but {' and '.join(parts)}.\n"
        return head + " found no differences.\n"
    out = [head + f" found {len(rows)} difference{'s' if len(rows) != 1 else ''}:", ""]
    for f in rows:
        page, approved = _pair(f)
        out += [f"{f.number}. [{short_verdict(f)}] ({f.item_id})",
                f"   Page says: “{plain(page)}”",
                f"   Approved copy says: “{plain(approved)}”"]
        if f.explanation:
            out.append(f"   Detail: {plain(f.explanation)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
