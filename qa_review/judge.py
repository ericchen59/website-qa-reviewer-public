"""Judgment and consistency items: one narrow model call each, with every quote validated.

A quote is valid only when it appears, after typographic normalization, inside a single
captured page block (KTD10). A verdict without a valid quote can never be PASS: it becomes
NOT FOUND ON PAGE. A prior verdict is reused, before any model call, when every block it
cited is unchanged (KTD13).
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pathlib
import re

from .checks import evidence_hash, similarity
from .model import ModelClient
from .schema import ChecklistItem, Finding, PageBlock
from .typography import normalize as _n

PROMPT = pathlib.Path(__file__).parent / "prompts" / "judge.md"
NOT_FOUND = "NOT FOUND ON PAGE"
JUDGE_SCHEMA = {"type": "object", "properties": {
    "verdict": {"type": "string", "enum": ["PASS", "FAIL", "WARN", "NOT_FOUND"]},
    "quote": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["verdict", "quote", "reason"]}
CONSISTENCY_SCHEMA = {"type": "object", "properties": {
    "verdict": {"type": "string", "enum": ["PASS", "INCONSISTENT"]},
    "quotes": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "required": ["verdict", "quotes", "reason"]}
_CURRENCY = re.compile(r"[$€£]\s?\d")
_PRICEY = re.compile(r"\b(price|prices|cost|fee|fees|amount)\b", re.I)
CAP = 15


@functools.lru_cache(maxsize=None)
def _template() -> str:
    return PROMPT.read_text(encoding="utf-8")


def _prompt(item, extra, verdict_rules, candidates):
    payload = [{"index": b.index, "text": b.text, "hidden": b.visible == "hidden"} for b in candidates]
    return (_template()
            .replace("{{ITEM}}", item.text).replace("{{EXTRA}}", extra)
            .replace("{{VERDICT_RULES}}", verdict_rules)
            .replace("{{BLOCKS}}", json.dumps(payload, ensure_ascii=False, indent=1)))


def _owner(quote: str, blocks: list[PageBlock], candidates: list[PageBlock] = ()):
    """The block a quote came from: prefer the candidates shown to the model, since a quote
    that also occurs earlier on the page (e.g. inside the tab title) must not be attributed
    to that unrelated block instead of the one actually judged."""
    q = _n(quote)
    if not q:
        return None
    for b in candidates:
        if q in _n(b.text):
            return b
    for b in blocks:
        if q in _n(b.text):
            return b
    return None


def _finding(item, verdict, blocks_used, quote, reason, candidates=()) -> Finding:
    cited = []
    for b in blocks_used:
        t = _n(b.text)
        if t not in cited:
            cited.append(t)
    basis = []
    for b in candidates:
        t = _n(b.text)
        if t not in basis:
            basis.append(t)
    return Finding(item_id=item.id, verdict=verdict, approved_text=item.text, quote=quote,
                   block=blocks_used[0].index if blocks_used else None, cited=cited,
                   evidence_hash=evidence_hash(cited) if cited else "", explanation=reason,
                   basis=basis)


def reuse_prior(prior: Finding, blocks: list[PageBlock]):
    """The prior finding, marked reused, if every candidate block the model was shown last
    round -- not just the ones its verdict cited -- is still present unchanged; else None.
    Checking `cited` alone let a whole-page or consistency PASS survive a change in an uncited
    candidate block (e.g. a new price section with no disclaimer, or the tab title flipping
    year while the H1 stayed the cited block): the reviewer would stay green while the page
    went red. Records without `basis` (pre-dating this field) fall back to `cited`-only."""
    if prior.verdict == NOT_FOUND or not prior.cited:
        return None
    present = {_n(b.text): b for b in blocks}
    basis = prior.basis or prior.cited
    if not all(c in present for c in basis):
        return None
    return dataclasses.replace(prior, reused=True, block=present[prior.cited[0]].index)


def _candidates(item, results, blocks):
    by_index = {b.index: b for b in blocks}
    keep: dict[int, PageBlock] = {}
    for ref in (item.refs or item.subjects):
        r = results.get(ref)
        if r is not None and r.block in by_index:
            keep[r.block] = by_index[r.block]
    if not item.refs and _PRICEY.search(item.text):
        for b in blocks:
            if b.kind == "block" and _CURRENCY.search(b.text):
                keep.setdefault(b.index, b)
    if not keep:
        scored = sorted(blocks, key=lambda b: -similarity(_n(item.text), _n(b.text)))
        keep = {b.index: b for b in scored[:5]}
    return sorted(keep.values(), key=lambda b: b.index)[:CAP]


def judge_item(item: ChecklistItem, results: dict, blocks: list[PageBlock], model: ModelClient,
               prior: Finding | None = None) -> Finding:
    if prior is not None:
        reused = reuse_prior(prior, blocks)
        if reused is not None:
            return reused
    candidates = _candidates(item, results, blocks)
    if item.refs:
        approved = "\n".join(f"- {results[r].approved_text}" for r in item.refs if r in results)
        extra = (f"The approved copy for the related items (attribute: {item.label}):\n{approved}\n"
                 "Decide whether the page text agrees with itself and with the approved copy on that attribute.")
        rules = ("Answer PASS when the page agrees everywhere; answer INCONSISTENT when the page "
                 "contradicts itself or the approved copy, and give at least two quotes that show the "
                 "contradiction. For PASS give one quote as evidence.")
        answer = model.ask(_prompt(item, extra, rules, candidates), CONSISTENCY_SCHEMA, item.id)
        owners = [_owner(q, blocks, candidates) for q in answer["quotes"]]
        if not answer["quotes"] or any(o is None for o in owners):
            return _finding(item, NOT_FOUND, [], "", "the quoted page text could not be found on the page",
                            candidates)
        if answer["verdict"] == "INCONSISTENT":
            if len({o.index for o in owners}) < 2:
                return _finding(item, NOT_FOUND, [], "", "a contradiction needs quotes from two different blocks",
                                candidates)
            return _finding(item, "OPEN — PAGE INCONSISTENT", owners, " | ".join(answer["quotes"]), answer["reason"],
                            candidates)
        return _finding(item, "PASS", owners, " | ".join(answer["quotes"]), answer["reason"], candidates)

    # OPEN — NEEDS MARKETING (schema.py) is deliberately not offered here: the Cadillac baseline
    # has no unsigned item to verify it against (CLAUDE.md 2.4), and a verdict the model can never
    # be checked against a real example is worse than one it can't reach at all. See PROMPTS.md.
    rules = ("Answer PASS when the page text satisfies the item, FAIL when it contradicts or omits "
             "what the item requires, WARN when it is doubtful, and NOT_FOUND when none of the blocks "
             "address the item. For PASS, FAIL and WARN give a quote.")
    answer = model.ask(_prompt(item, "", rules, candidates), JUDGE_SCHEMA, item.id)
    if answer["verdict"] == "NOT_FOUND":
        return _finding(item, NOT_FOUND, [], "", answer["reason"] or "no page text addresses this item",
                        candidates)
    owner = _owner(answer["quote"], blocks, candidates)
    if owner is None:
        return _finding(item, NOT_FOUND, [], "", "the quoted page text could not be found on the page",
                        candidates)
    return _finding(item, answer["verdict"], [owner], answer["quote"], answer["reason"], candidates)
