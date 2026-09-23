"""Shared data shapes: checklist items, page blocks, findings and the findings record."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

VERDICTS = (
    "PASS",
    "FAIL",
    "WARN",
    "OPEN — NEEDS MARKETING",
    "OPEN — PAGE INCONSISTENT",
    "NOT FOUND ON PAGE",
)
ITEM_TYPES = ("verbatim", "judgment", "structural")
VISIBILITY = ("visible", "hidden", "undetermined")


@dataclass
class ChecklistItem:
    """One checkable item. A consistency check is a judgment item with `refs` set."""

    id: str
    section: str
    type: str
    text: str
    section_title: str = ""
    locator: dict | None = None      # table cell: {"table": int, "row": int, "col": int}
    subjects: list[str] = field(default_factory=list)   # items a condition concerns
    refs: list[str] = field(default_factory=list)       # items a consistency check compares
    label: str = ""                                     # attribute name for a consistency check

    def __post_init__(self):
        if self.type not in ITEM_TYPES:
            raise ValueError(f"unknown item type: {self.type!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChecklistItem":
        return cls(**d)


@dataclass
class PageBlock:
    """One text block of the rendered page."""

    index: int
    kind: str                         # "block" or "title"
    text: str
    path: str
    visible: str = "visible"
    bbox: list[float] | None = None          # [x, y, width, height] in page coordinates
    anchor_bbox: list[float] | None = None   # nearest visible ancestor, for hidden blocks
    table: dict | None = None                # {"table": int, "row": int, "col": int}
    tag: str = ""

    def __post_init__(self):
        if self.visible not in VISIBILITY:
            raise ValueError(f"unknown visibility: {self.visible!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PageBlock":
        return cls(**d)


@dataclass
class Finding:
    item_id: str
    verdict: str
    quote: str = ""                   # the page text the verdict rests on
    approved_text: str = ""
    block: int | None = None          # index of the cited page block
    evidence_hash: str = ""           # hash of the cited blocks' normalized text
    cited: list[str] = field(default_factory=list)   # normalized text of each cited block
    basis: list[str] = field(default_factory=list)   # normalized text of every candidate block
                                                       # the model was shown, cited or not (KTD13)
    explanation: str = ""
    number: int | None = None         # one sequence shared by report lists and badges
    check_by_eye: bool = False        # WARN caused by undetermined visibility
    reused: bool = False              # verdict reused from the prior run

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(f"unknown verdict: {self.verdict!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**d)


@dataclass
class FindingsRecord:
    run_id: str
    baseline: dict                    # slug, hash, path
    page: dict                        # key, kind, snapshot, styles_vendored
    findings: list[Finding] = field(default_factory=list)
    typography_rules: list[str] = field(default_factory=list)
    items: list[ChecklistItem] = field(default_factory=list)   # the checklist reviewed

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "FindingsRecord":
        d = json.loads(text)
        return cls(
            run_id=d["run_id"],
            baseline=d["baseline"],
            page=d["page"],
            findings=[Finding.from_dict(f) for f in d["findings"]],
            typography_rules=d.get("typography_rules", []),
            items=[ChecklistItem.from_dict(i) for i in d.get("items", [])],
        )

    def counts(self) -> dict:
        out = {v: 0 for v in VERDICTS}
        for f in self.findings:
            out[f.verdict] += 1
        return out
