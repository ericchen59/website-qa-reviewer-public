"""Typographic normalization: a closed set of rules, nothing else.

Everything outside this set is compared character for character: asterisks, daggers,
dashes, casing and abbreviation periods are never folded, so a dropped asterisk or a
`vs.` / `vs` difference can never be normalized away.
"""

import functools
import re

_CURLY = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
}
_CURLY_RE = re.compile("[" + "".join(_CURLY) + "]")
_NBSP_RE = re.compile("[  ]")
_WS_RE = re.compile(r"\s+")

RULES = ("curly quotes to straight", "non-breaking space to space", "whitespace collapsed")


def normalize_with_rules(text: str) -> tuple[str, list[str]]:
    """Return the normalized text and the names of the rules that changed something."""
    applied: list[str] = []
    out = text
    if _CURLY_RE.search(out):
        out = _CURLY_RE.sub(lambda m: _CURLY[m.group(0)], out)
        applied.append(RULES[0])
    if _NBSP_RE.search(out):
        out = _NBSP_RE.sub(" ", out)
        applied.append(RULES[1])
    collapsed = _WS_RE.sub(" ", out).strip()
    if collapsed != out:
        applied.append(RULES[2])
    return collapsed, applied


@functools.lru_cache(maxsize=None)
def normalize(text: str) -> str:
    return normalize_with_rules(text)[0]
