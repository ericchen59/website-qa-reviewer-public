"""The runner: exactly one verdict per checklist item, or a hard error (R8).

Verbatim items are decided first (deterministic), then structural and judgment items, which
read those results. The set of verdicts must equal the set of checklist items; anything else
raises CoverageError and nothing downstream runs, so no report can present itself as complete.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import checks, judge
from .model import ModelClient
from .schema import ChecklistItem, Finding, PageBlock
from .typography import RULES, normalize_with_rules


class CoverageError(RuntimeError):
    pass


@dataclass
class ReviewResult:
    findings: list[Finding]
    typography_rules: list[str] = field(default_factory=list)


def run_review(items: list[ChecklistItem], blocks: list[PageBlock], model: ModelClient,
               prior: dict | None = None) -> ReviewResult:
    """prior maps item id -> Finding from the previous round (for verdict reuse)."""
    if not items:
        raise CoverageError("coverage contract broken: the checklist has no items to review")
    prior = prior or {}
    by_index = {b.index: b for b in blocks}
    results: dict[str, Finding] = {}
    rules: set[str] = set()
    seen_texts: dict[str, int] = {}

    for item in items:
        if item.type != "verbatim":
            continue
        key, item_rules = normalize_with_rules(item.text)
        occurrence = seen_texts.get(key, 0)
        seen_texts[key] = occurrence + 1
        f = checks.check_verbatim(item, blocks, occurrence)
        if f is None:
            continue
        results[item.id] = f
        rules.update(item_rules)
        if f.block in by_index:
            rules.update(normalize_with_rules(by_index[f.block].text)[1])

    for item in items:
        if item.type == "verbatim":
            continue
        if item.type == "structural":
            f = checks.check_structural(item, results, blocks)
        else:
            f = judge.judge_item(item, results, blocks, model, prior.get(item.id))
        if f is not None:
            results[item.id] = f

    findings = [results[i.id] for i in items if i.id in results]
    counts = Counter(f.item_id for f in findings)
    missing = [i.id for i in items if i.id not in counts]
    dupes = sorted(x for x, n in counts.items() if n > 1)
    if missing or dupes:
        raise CoverageError(
            "coverage contract broken: " +
            (f"no verdict for {', '.join(missing)}" if missing else "") +
            ("; " if missing and dupes else "") +
            (f"more than one verdict for {', '.join(dupes)}" if dupes else ""))
    return ReviewResult(findings, [r for r in RULES if r in rules])
