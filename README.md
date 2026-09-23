# Website QA Reviewer

Ground truth baselines for QA-ing agency-built web pages against corporate-marketing-approved copy.

## Contents

| File | Purpose |
| --- | --- |
| `GROUND-TRUTH_ct5v-vs-ct5v-blackwing.md` | Baseline, generated from a page capture by `fixtures/baseline-from-capture.py` |
| `GROUND-TRUTH_ct5v-vs-ct5v-blackwing.docx` | Generated Word version for circulation/sign-off |
| `md2docx.py` | Markdown → .docx converter (stdlib only, preserves real Word tables) |
| `qa_review/`, `.claude/skills/qa-review/` | The reviewer: intake, capture, checks, runner, diff, reports, overlay |
| `tests/` | Unit tests (`python3 -m unittest discover -s tests`) |
| `fixtures/` | Page captures, the seeded agency rebuild, the answer key, and the naive-prompt runner |
| `PROMPTS.md` | Build journal — every prompt verbatim, what came back, what changed |

## The reviewer

`/qa-review <baseline> <url-or-file>` (a Claude Code skill in `.claude/skills/qa-review/`) checks an
agency page against an approved-copy baseline and hands back a failures-first report, a block to
paste to the agency, a round-over-round diff and an annotated page. Copy only; every checklist item
gets a verdict or the run fails.

```
pip install -r requirements.txt        # Python 3.11+, plus Chrome
python3 -m qa_review intake   GROUND-TRUTH_*.md            # build and print the checklist
python3 -m qa_review confirm  GROUND-TRUTH_*.md            # once per baseline version
python3 -m qa_review review   GROUND-TRUTH_*.md <url-or-file>
python3 -m unittest discover -s tests                      # browser tests skip without Chrome
```

`runs/` (findings, snapshots, reports) and the saved browser login (`~/.qa-review/profile`) hold
confidential material and are never committed. `python3 -m qa_review clean --profile --all-runs`
removes them. Baseline and page text go to the model through the local `claude` CLI.

## Workflow

1. The `.md` is the source of truth and diffs cleanly in git. It is generated from a capture of the
   page (`python3 fixtures/baseline-from-capture.py <capture.html> <out.md>`); see `CLAUDE.md` §2.6.
2. Regenerate the Word doc:
   ```
   python3 md2docx.py GROUND-TRUTH_ct5v-vs-ct5v-blackwing.md GROUND-TRUTH_ct5v-vs-ct5v-blackwing.docx
   ```
3. Circulate the `.docx` for Marketing sign-off; commit both.

Do not hand-edit the `.docx` — changes there are overwritten on the next regeneration.

## Scope

Baselines currently cover **copy only**: headings, body copy, spec values, option/package
claims, CTA labels and disclaimers. Images, layout, elements and animations are out of
scope and will be added as separate baseline sections later.
