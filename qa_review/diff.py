"""The round diff (R17): what changed since the previous round.

An ID is fixed, regressed or new only when its recorded page evidence changed. A verdict that
differs over identical evidence is flagged for review instead. An ID replaced after a baseline
edit is listed as "replaces <old>" whatever its verdict, and is never credited as fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pairing import pair_retired
from .schema import FindingsRecord

PASSING = "PASS"


@dataclass
class DiffEntry:
    item_id: str
    category: str      # fixed | still open | new | regressed | verdict changed, page unchanged | replaces
    prior_verdict: str = ""
    verdict: str = ""
    replaces: str = ""


@dataclass
class Pairing:
    old_id: str
    new_id: str
    old_text: str
    new_text: str


@dataclass
class Removed:
    item_id: str
    text: str


@dataclass
class RoundDiff:
    entries: list[DiffEntry] = field(default_factory=list)
    unchanged: int = 0
    pairs: list[Pairing] = field(default_factory=list)
    removed: list[Removed] = field(default_factory=list)


def diff_records(prior: FindingsRecord | None, current: FindingsRecord) -> RoundDiff | None:
    if prior is None:
        return None
    p_by = {f.item_id: f for f in prior.findings}
    c_by = {f.item_id: f for f in current.findings}
    p_items = {i.id: i for i in prior.items}
    c_items = {i.id: i for i in current.items}

    # Consistency checks are proposed by the intake model, not written by the PMM: a different
    # set between rounds is not a baseline edit, so they never pair or count as removed.
    retired = [p_items[i] for i in p_by if i not in c_by and i in p_items and not p_items[i].refs]
    added = [c_items[i] for i in c_by if i not in p_by and i in c_items and not c_items[i].refs]
    pair_map, removed_ids, _ = pair_retired(retired, added)
    successors = {new: old for old, new in pair_map.items()}

    d = RoundDiff()
    for f in current.findings:
        old = p_by.get(f.item_id)
        if old is None:
            if f.item_id in successors:
                d.entries.append(DiffEntry(f.item_id, "replaces", p_by[successors[f.item_id]].verdict,
                                           f.verdict, replaces=successors[f.item_id]))
            elif f.verdict != PASSING:
                d.entries.append(DiffEntry(f.item_id, "new", "", f.verdict))
            else:
                d.unchanged += 1
            continue
        was_pass, is_pass = old.verdict == PASSING, f.verdict == PASSING
        same_evidence = old.evidence_hash == f.evidence_hash
        if was_pass and is_pass:
            d.unchanged += 1
        elif not was_pass and not is_pass:
            d.entries.append(DiffEntry(f.item_id, "still open", old.verdict, f.verdict))
        elif same_evidence:
            d.entries.append(DiffEntry(f.item_id, "verdict changed, page unchanged", old.verdict, f.verdict))
        elif is_pass:
            d.entries.append(DiffEntry(f.item_id, "fixed", old.verdict, f.verdict))
        else:
            d.entries.append(DiffEntry(f.item_id, "regressed", old.verdict, f.verdict))

    for old_id, new_id in pair_map.items():
        d.pairs.append(Pairing(old_id, new_id, p_items[old_id].text, c_items[new_id].text))
    d.removed = [Removed(i, p_items[i].text) for i in removed_ids]
    return d
