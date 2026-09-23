#!/usr/bin/env python3
"""Run the naive whole-document prompt against a page capture. Reproduces iteration 1.

This approximates the approach the PMM's Glean agent takes: one shot, whole ground-truth
document, whole page, "compare these and report inconsistencies." It is an approximation,
not her tool — different model, different retrieval.

The page reaches the model as plain extracted text, deliberately: that is what a retrieval
layer hands an LLM. No markup, no visibility information.

The run is isolated from this repo's CLAUDE.md, answer key and memory: it executes from a
scratch directory with no tools, no MCP servers and no settings sources, so the model sees only
the prompt below.

Usage:
    python3 fixtures/naive-run.py <page.html> <baseline.md> <output.md>
"""

import datetime
import html
import pathlib
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

MODEL = "claude-sonnet-5"
PROMPT = pathlib.Path(__file__).parent / "naive-prompt.md"

BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "footer", "header"}
SKIP = {"script", "style", "noscript", "svg", "head"}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self.in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in SKIP:
            self.skip += 1
        if tag in BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in SKIP and self.skip:
            self.skip -= 1
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def page_text(raw_html: str) -> str:
    # <title> lives in <head>, which is skipped as a block; capture it separately.
    p = TextExtractor()
    p.feed(raw_html)
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.S)
    title = html.unescape(m.group(1)).strip() if m else ""
    body = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    body = re.sub(r"\n\s*\n+", "\n", body).strip()
    return f"Page title: {title}\n\n{body}"


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    page_path, baseline_path, out_path = map(pathlib.Path, sys.argv[1:])

    prompt = (
        PROMPT.read_text(encoding="utf-8")
        .replace("{{GROUND_TRUTH}}", baseline_path.read_text(encoding="utf-8"))
        .replace("{{PAGE_TEXT}}", page_text(page_path.read_text(encoding="utf-8")))
    )

    with tempfile.TemporaryDirectory() as scratch:
        res = subprocess.run(
            ["claude", "-p", "--model", MODEL, "--tools", "", "--setting-sources", "",
             "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"],
            input=prompt, capture_output=True, text=True, cwd=scratch,
        )
    if res.returncode != 0:
        print(res.stderr)
        return res.returncode

    header = (
        f"<!-- naive whole-document run\n"
        f"     date:     {datetime.date.today()}\n"
        f"     model:    {MODEL}\n"
        f"     page:     {page_path.name}\n"
        f"     baseline: {baseline_path.name}\n"
        f"     prompt:   fixtures/naive-prompt.md (verbatim)\n"
        f"     input:    {len(prompt):,} chars\n"
        f"     Unedited model output follows. -->\n\n"
    )
    out_path.write_text(header + res.stdout, encoding="utf-8")
    print(f"wrote {out_path} ({len(res.stdout):,} chars of output, {len(prompt):,} chars of input)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
