"""Shared test helpers: paths, a stub intake model, and docx generation."""

import json
import pathlib
import re
import subprocess
import sys
import tempfile

from qa_review.model import StubModel

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "GROUND-TRUTH_ct5v-vs-ct5v-blackwing.md"

MINI = """# Ground Truth

## Page Identity

**Headline**

> Widget Deluxe 2026

**Tab title**

> Widget Deluxe 2025 | Shop

## Buttons

> Buy now

> Buy now

## Specs

| Widget | Spec label | Widget Pro |
| --- | --- | --- |
| $10 | Price* | $20 |

## Legal

**Conditions:**

1. The note is present whenever any price appears.
2. The note is visible on page load.

> *Price excludes tax.
"""


def to_docx(md_path: pathlib.Path, out: pathlib.Path) -> pathlib.Path:
    subprocess.run([sys.executable, str(ROOT / "md2docx.py"), str(md_path), str(out)],
                   check=True, capture_output=True)
    return out


def write_tmp(text: str, suffix=".md") -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / f"baseline{suffix}"
    p.write_text(text, encoding="utf-8")
    return p


def intake_stub(structural_index=None, consistency_marker=None):
    """A stub for the intake model call that answers from the item list in the prompt."""

    def answer(prompt: str):
        payload = json.loads(re.search(r"<<<ITEMS(.*?)ITEMS>>>", prompt, re.S).group(1))
        items, conds = payload["items"], payload["conditions"]
        subject_ids = [i["id"] for i in items if i["text"].lstrip().startswith("*")][:1]
        out = {"conditions": [], "consistency": []}
        for c in conds:
            typ = "structural" if c["index"] == structural_index else "judgment"
            out["conditions"].append({"index": c["index"], "type": typ, "subjects": subject_ids})
        if consistency_marker:
            refs = [i["id"] for i in items if consistency_marker in i["text"]]
            if len(refs) >= 2:
                out["consistency"].append({"label": "model year", "refs": refs,
                                           "text": "The model year is the same everywhere it appears."})
        return out

    return StubModel({"intake": answer})
