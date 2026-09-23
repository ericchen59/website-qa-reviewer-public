# Answer Key — CT5-V vs. CT5-V Blackwing demo

What the reviewer *should* return, per run, against `GROUND-TRUTH_ct5v-vs-ct5v-blackwing.md`.

That baseline is **extracted from the page**, not hand-written: `baseline-from-capture.py` reads
`live-2026-09-20-recapture.html` and reproduces the committed file byte for byte. Every boxed
quote, header cell and spec-table cell is verified present in both captures. So the baseline is
faithful, and defects can only live on the **page** — the agency altered approved copy or broke
the page's structure. The approved copy is never edited to disagree with the page.

---

## Fixtures

| File | What it is | Use |
| --- | --- | --- |
| `live-2026-09-20.html` | Pristine capture of the live page, via `capture.js`. Untouched. | Run A; source for the rebuild |
| `live-2026-09-20-recapture.html` | Second capture, same day. Visible copy identical to the first; only an injected accessibility-widget notice differs. | Source for the baseline |
| `agency-rebuild-2026-09-20.html` | The pristine capture with six defects, applied by `seed-defects.py`. | Run B |
| `baseline-from-capture.py` | Extracts the baseline from a capture. Aborts if the page's block structure changes. | Baseline |
| `seed-defects.py` | Regenerates the rebuild. Aborts unless each target matches exactly once. | Reproducibility |
| `capture.js` | Headed-Chrome Playwright capture. Cloudflare 403s curl and headless; headed with a persistent profile passes. | Re-capture |
| `naive-prompt.md`, `naive-run.py` | The naive whole-document prompt and its isolated runner. | Act 1 |
| `live-2026-09-20-vendored.html`, `agency-rebuild-vendored-2026-09-20.html` | The two captures above made self-contained by `python3 -m qa_review vendor` (stylesheets and assets inlined, active content stripped). They render the same offline, so visibility is determinable. **These are the scored inputs**; the originals are untouched and also pass the verdict checks, but their disclaimer-visibility condition comes back `WARN` (check by eye) because their styles are remote. | Runs A-C |
| `GROUND-TRUTH_ct5v-edited-intro.md` | Throwaway copy of the baseline with one approved line rewritten (`nearly two decades` to `over two decades`). Never a substitute for the committed baseline (§2.6). | Run C |
| `superseded/` | Naive outputs from the retired v1.3 seeded baseline. Real artifacts, kept as history. | — |

---

## Run A — pristine capture

`live-2026-09-20.html` against the baseline.

Expected: **0 FAIL, 1 `OPEN — PAGE INCONSISTENT`, everything else PASS.** A verdict missing from
that set is a silent miss — the exact failure this build exists to make structurally impossible.
Nothing in this baseline is `OPEN — NEEDS MARKETING`; see below.

### Found unaided — not seeded

| Section | Finding | Verdict |
| --- | --- | --- |
| Page Identity | Tab title says **2025** CT5-V Blackwing; H1, breadcrumb and spec-table headers all say **2026** | **OPEN — PAGE INCONSISTENT** |

A genuine live-page error, visible directly in the capture: `<title>` reads
`2026 CT5-V vs. 2025 CT5-V Blackwing Comparison`, the H1 reads `2026 CT5-V vs. 2026 CT5-V
Blackwing Comparison`. The baseline records the tab title exactly as the page renders it, so
nothing flags it — the reviewer has to derive it by cross-referencing four items that each
individually match. Nothing here is seeded and nothing is hand-edited, which forecloses "you
planted that."

The agency is not on the hook until Marketing rules on the fix — hence `OPEN — PAGE
INCONSISTENT` rather than FAIL.

### Not exercised: `OPEN — NEEDS MARKETING`

The baseline used to carry a Premium Options table whose three Blackwing interior items read
"cost status not stated on page," which was this verdict's live example. The PMM's Word pass
removed the table on 2026-09-20, so no run here produces it. A baseline that leaves something
unsigned is needed to show it — the second, minimal baseline (`CLAUDE.md` §6 step 4) is the
candidate.

---

## Run B — seeded agency rebuild

`agency-rebuild-2026-09-20.html` against the baseline. Everything in Run A, **plus** six FAILs.

| # | Kind | Section | Approved copy | Page says | Baseline rule | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| P4 | Copy | Spec table | `$57,600` | `$58,900` | Boxed table cell | **FAIL** |
| P5 | Copy | Introduction | `nearly two decades of relentless engineering` | `over two decades of relentless engineering` | Boxed quote | **FAIL** |
| P6 | Copy | Disclaimer | six exclusions incl. `dealer fees` | `dealer fees` absent | Condition 3 | **FAIL** |
| P1 | Structure | Spec table label | `Starting MSRP*` | `Starting MSRP` | Condition 2 | **FAIL** |
| P2 | Structure | Disclaimer | visible text on page load | wrapped in `<details>` behind "Read more" | Condition 5 | **FAIL** |
| P3 | Copy | Exterior | `finishes that include polished silver…` | `three finishes: polished silver…` | Boxed quote | **FAIL** or **WARN** |

**P2 is the one plain text extraction cannot see.** The disclaimer's text is unchanged; only its
visibility differs. A reviewer that only compares strings passes condition 5 here — a silent
miss on camera. Catching it needs the `on_load_visible` flag (`CLAUDE.md` §3), computed by
walking ancestors for `<details>`, `hidden`, `aria-hidden`, `display:none` and accordion classes.

**P5:** the page's claim may even be true (V-Series launched in 2004). Approved copy is the
standard, not the truth; an unapproved claim change is a substantiation problem regardless.

**P3 is a deliberate severity judgment.** §2.7 puts "illustrative list presented as exhaustive"
under WARN and "verbatim copy altered" under FAIL, and P3 is both. Either verdict is defensible;
a reviewer that flags it and *explains the exhaustiveness shift* is doing the job. One that
reports only "text differs" has missed why it matters.

**P6 is the one that matters legally.** An approved exclusion dropped from a legal sentence is
compliance exposure, not a typo — and it is an *absence*, the class a whole-document read is
worst at.

Naive-run results against these fixtures belong in the build journal (`PROMPTS.md`), not here — this file says
what the right answer is, not how any tool did.

---

### How the six defects map to report rows

Six defects, but the reviewer reports **eight** FAIL rows against the rebuild: P1 (dropped asterisk)
also trips the numbered condition "the asterisk matches the `Starting MSRP*` label", and P6 (dropped
`dealer fees`) also trips "all six exclusions appear". Both are the same root cause, reported once per
baseline item that states it. The asterisk condition is a model-judged item and came back `WARN` in one
live run and `FAIL` in another, so score it as "flagged, either severity". Everything else is
deterministic and must not vary between runs.

---

## Run C — the PMM accepts the agency's wording (round 2, edited baseline)

`GROUND-TRUTH_ct5v-edited-intro.md` against `agency-rebuild-vendored-2026-09-20.html`, run **after** Run B so
Run B is its prior round. The PMM has rewritten the approved introduction to match what the agency built (P5).

Expected: the introduction item has a new ID marked with a dagger and listed in the round diff as
"replaces <old ID>", passing. The old ID is **not** credited as fixed. A footnote gives the old and new approved
text. The other defects are still open. Model-proposed consistency checks may differ between intakes and are never
reported as baseline edits. The agency block carries no dagger.

---

## Traps — must NOT be reported as failures

The baseline carries no notes saying these are intentional. The page matches the boxed quotes, so
character-for-character comparison passes them. A run that flags one is a **reviewer defect, not
a baseline defect**.

| Section | The trap |
| --- | --- |
| Page Identity / spec heading | H1 uses `vs.` with a period; the spec section heading uses `vs` without one. Both as on the page. A reviewer that "fixes" one to match the other is wrong. |
| Spec table vs. narrative | Table uses `HP` / `LB-FT TQ`; narrative spells units out lowercase. Intentional split. |
| Exterior claims | On the pristine page the finish list is illustrative — "finishes that include". Not exhaustive, not a defect. (Only the rebuild breaks this — P3.) |
| Interior claims | Blackwing-exclusive list is introduced as "Examples of features…" — illustrative. |

**Not exercised: apostrophe normalization.** The baseline is verbatim, so it carries the page's
curly apostrophes and there is nothing to normalize between the two. The rule still belongs in
the reviewer (a PMM's Word document will not match a page's typography), but no run here tests it;
a unit test on the normalizer has to.

---

## What the baseline does not assert

The baseline is approved copy only — no claims tables, formatting rules or consistency checks.
Consequences worth knowing before scoring a run:

- **No closed-world assertion.** Nothing licenses the reviewer to flag copy the page *added* — an
  unapproved second legal line, say. That check class is unenforceable.
- **Narrative↔spec-table consistency is not stated.** The figures agree, so a reviewer can derive
  the cross-reference, but the doc does not assert it. This is why no fixture seeds a
  narrative/table disagreement: a miss would look like a reviewer bug when it is a baseline gap.
- **WARN is close to unreachable.** Both §2.7 WARN classes depended on notes the baseline does not
  carry; what remains reduces to verbatim mismatch, which is FAIL. P3 is the nearest thing to a
  genuine WARN, and it is arguable. Say so plainly rather than manufacturing a WARN.
- For the same reason, collapsing the Suspension or Trunk Cargo Volume rows to "same" is not
  seeded: the rule forbidding it is not in the doc.

---

## Caveat

All fixtures are frozen captures from 2026-09-20 and are committed, so runs are reproducible
regardless of what the live site does. Re-running `capture.js` may produce different values —
re-verify before scoring, and do not assume the model-year mismatch survives indefinitely: it is
a real defect the dealer may fix.
