"""The one-screen checklist the PMM confirms (R3)."""

from .intake import Checklist

_WORDS = 6


def _gist(text: str, n: int = _WORDS) -> str:
    words = text.split()
    return " ".join(words[:n]) + ("\u2026" if len(words) > n else "")


def render_view(cl: Checklist) -> str:
    counts = cl.counts_by_type()
    g = cl.guard
    by_id = {i.id: i for i in cl.items}
    if not g.get("applicable"):
        guard = ("Count guard: not applicable (no boxed quotes, table cells or numbered conditions "
                 "were found in the source), so this list is the only check that nothing was dropped.")
    else:
        s = g["source"]
        guard = (f"Count guard: passed (verbatim {s['verbatim']}/{g['checklist']['verbatim']}, "
                 f"conditions {s['conditions']}/{g['checklist']['conditions']}).")
    lines = [f"# Checklist \u2014 {cl.baseline['slug']}", "",
             f"Counts by type: verbatim {counts['verbatim']}, judgment {counts['judgment']}, "
             f"structural {counts['structural']} ({len(cl.items)} items)", guard, ""]
    section = None
    for i in cl.items:
        if i.section_title != section:
            section = i.section_title
            lines += ["", f"## {section}"]
        first = " ".join(i.text.split()[:8])
        suffix = "\u2026" if len(i.text.split()) > 8 else ""
        # The model chose subjects/refs during intake; showing them is what lets the PMM
        # catch a condition bound to the wrong item, or a consistency check comparing the
        # wrong pair, instead of that choice going unseen until review runs against it.
        extra = ""
        if i.subjects:
            about = ", ".join(_gist(by_id[s].text) if s in by_id else s for s in i.subjects)
            extra = f" \u2014 about: {about}"
        elif i.refs:
            across = ", ".join(_gist(by_id[r].text) if r in by_id else r for r in i.refs)
            extra = f" \u2014 {i.label!r} across: {across}"
        lines.append(f"- `{i.id}` \u00b7 {i.type} \u00b7 {first}{suffix}{extra}")
    return "\n".join(lines) + "\n"
