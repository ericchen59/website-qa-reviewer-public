"""Pair a retired ID with its replacement after the PMM edits an approved line (KTD12).

Only an unambiguous match pairs: within one section, same item type, each side's best
match for the other above the floor, and clearly ahead of the runner-up. Anything else is
reported as removed plus added.
"""

from __future__ import annotations

from .checks import similarity
from .schema import ChecklistItem
from .typography import normalize as _n

FLOOR = 0.6
MARGIN = 0.1


def _best_two(scores: list[float]):
    ordered = sorted(scores, reverse=True)
    return ordered[0], (ordered[1] if len(ordered) > 1 else 0.0)


def pair_retired(retired: list[ChecklistItem], added: list[ChecklistItem]):
    """Return (pairs {old_id: new_id}, removed [old_id], unpaired_added [new_id])."""
    score = {(o.id, a.id): (similarity(_n(o.text), _n(a.text))
                            if o.section == a.section and o.type == a.type else 0.0)
             for o in retired for a in added}
    pairs: dict[str, str] = {}
    for o in retired:
        row = [score[(o.id, a.id)] for a in added]
        if not row:
            continue
        best, second = _best_two(row)
        if best < FLOOR or best - second < MARGIN:
            continue
        a = added[row.index(best)]
        col = [score[(x.id, a.id)] for x in retired]
        cbest, csecond = _best_two(col)
        if cbest == best and (cbest - csecond >= MARGIN) and retired[col.index(cbest)].id == o.id:
            pairs[o.id] = a.id
    removed = [o.id for o in retired if o.id not in pairs]
    paired_new = set(pairs.values())
    return pairs, removed, [a.id for a in added if a.id not in paired_new]
