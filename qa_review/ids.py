"""Stable item IDs: a section slug plus a short hash of the normalized approved text."""

import hashlib
import re

from .typography import normalize


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", normalize(text).lower()).strip("-")
    return s or "item"


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:6]


def item_id(section_slug: str, text: str, ordinal: int = 0) -> str:
    """Editing the text changes the ID; typography and whitespace do not.
    Identical texts in one section take an ordinal suffix."""
    h = _hash(normalize(text))
    return f"{section_slug}.{h}" + (f"-{ordinal + 1}" if ordinal else "")


def consistency_id(refs: list[str], label: str) -> str:
    return "consistency." + _hash("|".join(sorted(refs)) + "|" + slugify(label))
