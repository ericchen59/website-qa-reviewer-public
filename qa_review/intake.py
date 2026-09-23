"""Baseline intake: an approved-copy document becomes a typed, ID'd, frozen checklist.

Deterministic first (KTD7): boxed quotes and body table cells become verbatim items, numbered
conditions are collected, and the count guard re-counts the raw source by a second, simpler
pass. The model only types the conditions, names their subject items and proposes
cross-item consistency checks; code validates everything it returns.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from dataclasses import dataclass, field

from . import docx_reader
from .elements import Element
from .ids import consistency_id, item_id, slugify
from .model import ModelClient
from .schema import ChecklistItem
from .typography import normalize

PROMPT = pathlib.Path(__file__).parent / "prompts" / "normalize.md"
INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "conditions": {"type": "array", "items": {"type": "object", "properties": {
            "index": {"type": "integer"},
            "type": {"type": "string", "enum": ["judgment", "structural"]},
            "subjects": {"type": "array", "items": {"type": "string"}}},
            "required": ["index", "type", "subjects"]}},
        "consistency": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"},
            "refs": {"type": "array", "items": {"type": "string"}},
            "text": {"type": "string"}},
            "required": ["label", "refs", "text"]}},
    },
    "required": ["conditions", "consistency"],
}


class IntakeError(RuntimeError):
    pass


@dataclass
class Checklist:
    items: list[ChecklistItem]
    baseline: dict                       # slug, hash, path
    guard: dict = field(default_factory=dict)   # applicable, ok, source, checklist

    @property
    def baseline_hash(self) -> str:
        return self.baseline["hash"]

    def counts_by_type(self) -> dict:
        out = {"verbatim": 0, "judgment": 0, "structural": 0}
        for i in self.items:
            out[i.type] += 1
        return out

    def to_json(self) -> str:
        return json.dumps({"baseline": self.baseline, "guard": self.guard,
                           "items": [i.to_dict() for i in self.items]}, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Checklist":
        d = json.loads(text)
        return cls([ChecklistItem.from_dict(i) for i in d["items"]], d["baseline"], d.get("guard", {}))


def file_hash(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- readers

_CONDITION = re.compile(r"^\d+\.\s+(.*)")
_INDENTED_QUOTE = re.compile(r"^\s+>")
_LOOSE_CONDITION = re.compile(r"^\s*\d+[.)]\s")          # a numbered line that isn't "N. " flush left
_BULLET_OR_FENCE = re.compile(r"^\s*[-*]\s|^\s*```")


def _strip_markup(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "")


def read_markdown(text: str) -> list[Element]:
    """Boxed quotes (`>`), table cells (`|`), numbered conditions (`N. `) and `#`/`##` headers.
    Anything that looks like a mistyped version of that grammar -- an indented quote, a `N)`
    or indented condition, a bulleted list or code fence -- fails intake by name instead of
    silently vanishing (a dropped item still counts as "checked" once it's gone). A condition's
    wrapped continuation lines (no special prefix, immediately following it) are folded into
    its text rather than dropped."""
    els: list[Element] = []
    quote: list[str] = []
    table = -1
    in_table = False
    row = -1
    open_condition: Element | None = None

    def flush_quote():
        if quote:
            els.append(Element("quote", " ".join(quote)))
            quote.clear()

    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()

        if _INDENTED_QUOTE.match(line):
            raise IntakeError(f"line {n}: an indented '>' quote is not read as approved copy "
                              f"(box it flush left instead): {line.strip()!r}")
        if _LOOSE_CONDITION.match(line) and not _CONDITION.match(line):
            raise IntakeError(f"line {n}: a numbered condition must be written 'N. ' flush left "
                              f"(not indented or paren-numbered): {line.strip()!r}")
        if _BULLET_OR_FENCE.match(line):
            raise IntakeError(f"line {n}: a bulleted list or code fence is not read as approved "
                              f"copy: {line.strip()!r}")

        if line.startswith(">"):
            in_table = False
            open_condition = None
            quote.append(line[1:].strip().replace("&nbsp;", "\u00a0"))
            continue
        flush_quote()
        if line.startswith("|"):
            open_condition = None
            cells = [c.strip().replace("&nbsp;", "\u00a0") for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            if not in_table:
                in_table, table, row = True, table + 1, -1
                kind, r = "header_cell", -1
            else:
                row += 1
                kind, r = "cell", row
            for col, c in enumerate(cells):
                els.append(Element(kind, c, table, r, col))
            continue
        in_table = False
        if line.startswith("## "):
            open_condition = None
            els.append(Element("section", line[3:].strip()))
        elif line.startswith("# "):
            open_condition = None
            els.append(Element("title", line[2:].strip()))
        elif not line.strip():
            open_condition = None
        else:
            m = _CONDITION.match(line)
            if m:
                el = Element("condition", _strip_markup(m.group(1)).strip())
                els.append(el)
                open_condition = el
            elif open_condition is not None:
                open_condition.text = f"{open_condition.text} {_strip_markup(line.strip())}".strip()
            # else: ordinary prose outside any tracked structure, ignored as before
    flush_quote()
    return els


def raw_counts_markdown(text: str) -> dict:
    quotes = len(re.findall(r"(?m)^>.*(?:\n>.*)*", text))
    cells = 0
    for run in re.findall(r"(?m)^\|.*(?:\n\|.*)*", text):
        rows = [l for l in run.splitlines() if not re.fullmatch(r"\|[\s:\-|]+\|?", l)]
        cells += sum(l.strip().strip("|").count("|") + 1 for l in rows[1:])
    return {"verbatim": quotes + cells, "conditions": len(re.findall(r"(?m)^\d+\.\s", text))}


# ------------------------------------------------------------- extraction

def extract_items(elements: list[Element]):
    """Deterministic extraction: (verbatim items, conditions)."""
    items: list[ChecklistItem] = []
    conditions: list[dict] = []
    seen: dict[tuple, int] = {}
    section, title = "preamble", "Preamble"
    for e in elements:
        if e.kind == "section":
            section, title = slugify(e.text), e.text
        elif e.kind in ("quote", "cell"):
            key = (section, normalize(e.text))
            n = seen.get(key, 0)
            seen[key] = n + 1
            loc = {"table": e.table, "row": e.row, "col": e.col} if e.kind == "cell" else None
            items.append(ChecklistItem(id=item_id(section, e.text, n), section=section,
                                       section_title=title, type="verbatim", text=e.text, locator=loc))
        elif e.kind == "condition":
            conditions.append({"index": len(conditions), "text": e.text, "section": section,
                               "section_title": title})
    return items, conditions


# ------------------------------------------------------------------ build

def _read(path: pathlib.Path):
    if path.suffix.lower() == ".docx":
        return docx_reader.read_docx(path), docx_reader.raw_counts(path)
    text = path.read_text(encoding="utf-8")
    return read_markdown(text), raw_counts_markdown(text)


def build_checklist(path, model: ModelClient) -> Checklist:
    path = pathlib.Path(path)
    elements, raw = _read(path)
    verbatim, conditions = extract_items(elements)

    applicable = bool(raw["verbatim"] or raw["conditions"])
    if not applicable and (verbatim or conditions):
        # Extraction found real items but the independent raw pass found none -- that's the
        # guard blind to its own source (adversarial:docx_reader.py:100), not an empty
        # baseline, and it must never be waved through as "not applicable".
        raise IntakeError(
            f"count guard: extraction found {len(verbatim)} verbatim units and {len(conditions)} "
            f"conditions in {path}, but the independent raw pass found none; treat this as a "
            "count-guard bug, not an empty baseline")
    if not applicable:
        raise IntakeError(
            f"nothing to review: no boxed quotes, table cells or numbered conditions were found "
            f"in {path}")
    guard = {"applicable": applicable, "ok": True,
             "source": raw, "checklist": {"verbatim": len(verbatim), "conditions": len(conditions)}}
    if applicable and (raw["verbatim"] != len(verbatim) or raw["conditions"] != len(conditions)):
        raise IntakeError(
            f"count guard: the source has {raw['verbatim']} verbatim units and {raw['conditions']} "
            f"conditions, but extraction produced {len(verbatim)} and {len(conditions)}")

    payload = {"items": [{"id": i.id, "section": i.section_title, "text": i.text} for i in verbatim],
               "conditions": [{"index": c["index"], "text": c["text"], "section": c["section_title"]}
                              for c in conditions]}
    prompt = PROMPT.read_text(encoding="utf-8").replace("{{ITEMS}}", json.dumps(payload, ensure_ascii=False))
    answer = model.ask(prompt, INTAKE_SCHEMA, "intake")

    ids = {i.id for i in verbatim}
    typed = {c["index"]: c for c in answer["conditions"]}
    if sorted(typed) != [c["index"] for c in conditions] or len(answer["conditions"]) != len(conditions):
        raise IntakeError("intake: the model dropped, duplicated or invented a condition")
    items = list(verbatim)
    seen_conditions: dict[tuple, int] = {}
    for c in conditions:
        t = typed[c["index"]]
        bad = [s for s in t["subjects"] if s not in ids]
        if bad:
            raise IntakeError(f"intake: condition {c['index'] + 1} names unknown subject items {bad}")
        if t["type"] == "structural" and not t["subjects"]:
            raise IntakeError(f"intake: condition {c['index'] + 1} is structural but names no subject "
                              "items; a visibility condition needs at least one")
        # Two conditions can repeat the same wording within a section (a hand-typed baseline
        # duplicating a line), same as verbatim items already handle above -- without an
        # ordinal they'd collide on one ID and run_review would reject the whole checklist.
        key = ("conditions-" + c["section"], normalize(c["text"]))
        n = seen_conditions.get(key, 0)
        seen_conditions[key] = n + 1
        cid = item_id("conditions-" + c["section"], c["text"], n)
        items.append(ChecklistItem(id=cid, section=c["section"], section_title=c["section_title"],
                                   type=t["type"], text=c["text"], subjects=t["subjects"]))
    for k in answer["consistency"]:
        bad = [r for r in k["refs"] if r not in ids]
        if bad or len(set(k["refs"])) < 2:
            raise IntakeError(f"intake: consistency check {k['label']!r} has unusable refs {bad}")
        items.append(ChecklistItem(id=consistency_id(k["refs"], k["label"]), section="consistency",
                                   section_title="Consistency checks", type="judgment",
                                   text=k["text"], refs=sorted(set(k["refs"])), label=k["label"]))
    baseline = {"slug": slugify(path.stem), "path": str(path), "hash": file_hash(path)}
    return Checklist(items, baseline, guard)


# ------------------------------------------------------- frozen checklist

def write_checklist(folder, checklist: Checklist) -> None:
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "checklist.json").write_text(checklist.to_json(), encoding="utf-8")


def load_frozen(folder) -> Checklist:
    return Checklist.from_json((pathlib.Path(folder) / "checklist.json").read_text(encoding="utf-8"))


def _content_hash(checklist: Checklist) -> str:
    return hashlib.sha256(checklist.to_json().encode("utf-8")).hexdigest()


def confirm(folder) -> None:
    """Stamp both the baseline's hash and the frozen checklist's own content hash. The baseline
    hash alone isn't enough: reverting an edited baseline back to its confirmed content re-runs
    intake (the checklist.json a different edit overwrote no longer matches), and a fresh model
    call can type conditions, subjects or consistency checks differently the second time. Binding
    to content means that regenerated-but-unseen checklist reads as unconfirmed, not as the one
    the PMM actually reviewed."""
    folder = pathlib.Path(folder)
    cl = load_frozen(folder)
    (folder / "confirmed.json").write_text(
        json.dumps({"baseline_hash": cl.baseline_hash, "content_hash": _content_hash(cl)}),
        encoding="utf-8")


def is_confirmed(folder, checklist: Checklist) -> bool:
    f = pathlib.Path(folder) / "confirmed.json"
    if not f.exists():
        return False
    d = json.loads(f.read_text(encoding="utf-8"))
    return (d.get("baseline_hash") == checklist.baseline_hash
            and d.get("content_hash") == _content_hash(checklist))
