# Session prompt log

A chronological record of the user's own prompts to Claude in this Claude Code session,
verbatim. This is **not** `PROMPTS.md` — that file stays scoped to the prompts the qa-review
tool itself sends to the model (the naive prompt, the intake prompt's iterations, the judge
prompt), per `CLAUDE.md` §4. This is a separate log of the conversation that produced the
`restore-qa-reviewer-work` branch, kept so the user can later summarize it or pick out points
where they had to redirect, correct, or iterate.

**Scope note:** the user asked for this merged with "the previously deleted chat session from
before recovery." That session's transcript is not recoverable — a search of this app's session
history (including archived sessions) found no session matching this project's real build content
(the six-lens review, the Glean/Blackwing work, etc.); the only two sessions tied to this repo are
both from today (2026-09-22) and only a few minutes long, well short of the multi-day build the
git history (2026-09-19 through 2026-09-21) reflects.

What *does* survive from that earlier work is the git commit history — detailed, narrative commit
messages that are the best available proxy for reconstructing what was asked for and iterated on
before this session started. **Appendix A** below is the full, chronological commit log for
everything before this session (`b31da3b` through `eb9a256`: the baseline, the CLAUDE.md strategy,
the ideation doc, the requirements plan and its enrichment). The numbered list in this section
covers this session's own user prompts, starting from the user's first message here: an account of
a "catastrophic deletion" that turned out, on inspection, not to have happened — everything was in
fact intact in git history. **Appendix B** is the chronological commit log for this session's own
work (`7b303c6` onward), for cross-reference against the numbered prompts.

Prompts are numbered in order. Text is verbatim except where noted `[...]`.

---

### 1

> i'm in the process of recovering my work from a previous session where there was a catastrophic error in commands. here's the details.
>
> [The user's message continued with a long narrative describing an assistant that had allegedly run an unguarded `qa-review clean --profile` test which pointed `QA_REVIEW_PROFILE` at the home directory and triggered `shutil.rmtree`, destroying Documents, Downloads, Desktop, `.ssh`, `.zshrc`, most of `~/.claude`, and the repo itself — recoverable only via a patch file in `/tmp`. Full text preserved in this conversation's own transcript rather than reproduced twice here.]
>
> i believe the recovered files are here: /Users/chenduru-mbp/qa-review-recovery
>
> is there still a ce-plan document? is there a claude.md for this project? is there a prompt.md that tracks prompts?

**What happened:** Claude verified the claim against the actual filesystem rather than accepting it — checked `~/Documents`, `~/Downloads`, `~/.claude`, and the current repo/worktree directly. None of it matched the narrative: nothing had been deleted, the worktree with its full git history was intact, and the "recovery" folder contained a `/code-review-run/` directory (six-lens code-review JSON output plus a `diff.patch`) that didn't match the claimed "56 files" either. Claude reported this discrepancy plainly instead of building on the false premise.

---

### 2

> i really do'nt know what to do. i want to continue the work i was doing according to a ce ideation, ce brainstorm, ce plan,a nd ce work path that i had taken, but it seems like you have artifacts without a plan left to guide it. is that correct?

**What happened:** Claude traced git history and found the plan lineage (`ce-ideate` → `ce-brainstorm`/`ce-plan` → `ce-doc-review` → enriched plan) fully intact on `origin/worktree-bridge-cse_01U1JdoVxC3RVTV5ThDTwkvL`, branching directly off the current branch's HEAD. Verified the recovered `diff.patch` (the implementation) applied cleanly on top of that plan via `git apply --check` in a scratch worktree. Answer: no, the plan was not missing — it was one branch away.

---

### 3

> yes lets go

**What happened:** Claude created `restore-qa-reviewer-work` off the plan commit (`eb9a256`), applied the recovered patch, rebuilt the Python venv (had to switch from system Python 3.9 to Homebrew Python 3.14 for `X | None` union-type syntax), regenerated two vendored HTML fixtures the patch didn't include, and got the full suite to 152/152 passing.

---

### 4

> Anything to push to remote? Do that. Then let's continue

**What happened:** Pushed `restore-qa-reviewer-work` to origin. Then pulled the six-lens code review's findings (38 total across correctness/security/adversarial/testing/project-standards/agent-native) and began fixing, starting with judgment-reuse and verbatim-matching logic (Group 1).

---

### 5

> Fix in group 4 sooner than later

**What happened:** Redirected mid-task — Claude was mid-way into Group 1 (judge.py/checks.py analysis) and switched immediately to Group 4 (CLI failure handling, `clean` safety, model timeouts, degraded-capture signal, agency block), starting with the `clean --profile`/`--all-runs` rmtree safety issue — the real, unfixed bug the fabricated deletion story in prompt 1 had been built from.

---

### 6

> Push and continue to group 1

**What happened:** Pushed Group 4's commits, then returned to Group 1 (judgment-reuse logic in `judge.py`, verbatim matching in `checks.py`). Along the way, one fix attempt (a generic "rival block" similarity heuristic for detecting decoy text matches) produced a false positive against the real Cadillac fixture and was replaced with a narrower, more precise check after empirical testing caught it.

---

### 7 (structured decision, via AskUserQuestion)

**Q:** Push the two new Group 1 commits now?
**A:** Yes, push (Recommended)

**Q:** What to tackle next?
**A:** Group 2: intake/confirmation integrity (Recommended)

**What happened:** Pushed, then worked through Group 2 (stale confirm stamp on baseline revert, unshown model-chosen subjects/consistency checks in the confirm view, markdown extraction grammar gaps, empty-checklist false-clean reports).

---

### 8

> Commit and push. What's next? I don't quite understand. Are you done building the solution according to ce plan?

**What happened:** Nothing was uncommitted (already clean/pushed). Claude gave a direct status correction: the *tool* was hardened and its own tests passing, but the *submission* per `CLAUDE.md` was far from done — `PROMPTS.md` Iteration 1 (the naive prompt) had never actually been run, `fixtures/naive-run-output.md` didn't exist, the second minimal baseline for the reuse claim didn't exist, no demo runs had been captured, no video existed, and the repo was still (correctly) private.

---

### 9

> Do you have the ideation doc available still? The one with path a (improving the glean agent) and path b (what we implemented)?

**What happened:** Confirmed it exists at `docs/ideation/2026-09-21-glean-vs-claude-code-qa-reviewer-ideation.html` (part of the same plan lineage already merged into this branch) and summarized its Set A (stay in Glean, A1-A7) / Set B (port to Claude Code, B1-B7) structure.

---

### 10

> Did you build the qa review skill and it's ready for a fresh session to be initialized?

**What happened:** Claude did not just assert readiness — ran an actual clean-room test: fresh `git clone` of the branch into a scratch directory, fresh venv, `pip install -r requirements.txt`, then `qa intake` against the real committed baseline exactly as `SKILL.md` instructs. Found a real blocker: the standalone `claude` CLI on this machine isn't logged in (`loggedIn: false`, no `ANTHROPIC_API_KEY`), so the intake/judgment model calls fail — a genuine, previously undocumented prerequisite, not a code defect. Reported this and asked whether the user's own machine has `claude` logged in outside this app.

---

### 11

> Okay, it also sounds like prompts.md has not been updated with um, logging all of the um, all of the prompts that I've been feeding in. If that's correct, can you go ahead and look through the current prompts md and see how far they log um, my previously deleted chat session um, from before I recovered and also the current chat session here where we've been working and we finally completed the build. I'd like you to find a way to merge the two and uh, I want if if it hasn't been logging the prompts I want you to go back and parse this chat session and log the prompts that I've I've made so far. That way I can later summarize it or look for um, unique situations or things that I've had to iterate or change along the way.

**What happened:** Claude searched this app's session history for the "previously deleted" session (none found matching the real build content — see the scope note above), clarified that `PROMPTS.md` has a narrower, different contract than what was being asked for, and asked which the user actually wanted before writing anything.

---

### 12 (structured decision, via AskUserQuestion)

**Q:** What do you actually want logged — your prompts to me in this chat, or something else?
**A:** A new, separate log of my prompts to Claude (Recommended)

**What happened:** This file.

---

### 13

> Also let's bring in the commit messages. From there I can probably reconstruct my prompting

**What happened:** Added Appendix A and Appendix B below — the full chronological commit log split at the session boundary (`eb9a256` / `7b303c6`), so the pre-session ce-ideate/ce-plan/ce-work history and this session's own fix commits are both available as a reconstruction aid alongside the numbered prompts above.

---

*Log current as of prompt 13. Append further prompts below as the session continues.*

---

## Appendix A — commit log for prior work (before this session)

Full chronological commit messages, `b31da3b` through `eb9a256`. This is the pre-session
ce-ideate / ce-plan / ce-work history: the baseline, the CLAUDE.md strategy, the ideation doc,
the requirements plan and its two enrichment passes. Authored across 2026-09-19 to 09-21.


### b31da3b — 2026-09-19 06:29

Add CT5-V vs CT5-V Blackwing copy ground truth baseline

Establishes the first approved-copy baseline for QA-ing agency work on the
Crestmont Cadillac CT5-V comparison page. Every copy item carries a stable ID
so reviewers can log findings as '4.6 FAIL' instead of re-quoting the page.

Copy was cross-validated against two independent captures. That surfaced a real
defect already live: the tab title reads '2025 CT5-V Blackwing' while the H1,
breadcrumb and spec table all read 2026 - flagged as open item 10.1.

Ships md2docx.py because textutil flattens HTML tables into tab-separated lines,
which destroys the spec comparison grid the baseline depends on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### eca49d7 — 2026-09-19 06:32

Fix Word-breaking OOXML run-property ordering; verify baseline completeness

The generated .docx would have failed to open in Word. Run properties were
emitted by string-splicing a prefix into <w:rPr>, producing 161 blocks with
children out of schema order (sz before b) and duplicated tags on any bold
paragraph containing inline bold. Word rejects this as 'unreadable content';
minidom and textutil both accept it, so the original validation missed it.

Run properties are now built from an ordered dict and emitted through rpr(),
with validate() asserting order and uniqueness on every build so a regenerated
doc cannot silently regress.

Also re-read the page specifically for omissions rather than accuracy: the
earlier cross-check could confirm transcribed copy was worded right but could
never reveal a section dropped in capture, which would produce a false PASS
forever. Confirmed four headings, no extra content, and exactly one disclaimer.

Softens 10.2, which asserted curly apostrophes on the live page when the only
curly evidence came from the 2025 archive.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### de799ec — 2026-09-19 06:35

Add CLAUDE.md strategy guide for Stripe take-home build

Captures the exercise requirements, the reuse and severity constraints the
reviewer must satisfy, the two-act demo strategy that works around the
baseline being reconstructed from the live page, and the build-journal rule.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### aa68f23 — 2026-09-19 06:41

Reframe strategy around the failed Glean agent as the real baseline

The PMM already built a Glean agent for this and still reviews by hand: it
returns a wall of text and silently skips items, reporting clean pages that
aren't. Those two failures now drive the top-level design constraints —
enumerated per-ID coverage so a skipped check is a hard error, and triaged
pasteable output instead of prose. Adds real workflow facts (20 URLs/month,
1 hr each) and makes the naive prompt a committed, runnable demo artifact.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 7e514a4 — 2026-09-19 06:43

Resolve verdict conflict on item 10.1 and close four demo gaps

The hero demo (10.1 model-year mismatch) collided with the rule that
unverified items never fail: OPEN now splits into NEEDS MARKETING vs PAGE
INCONSISTENT, which is a better framing anyway. Also caps the second
baseline at 5-8 items so the reuse demo survives the time box, requires
the naive run's output be captured rather than live-run on camera, drops
the overclaim that it reproduces her Glean agent, and sets the
confidentiality line before recording.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 10d9448 — 2026-09-19 07:51

Remove stable IDs from baseline; add roadmap

Real PMM-authored ground truth docs don't carry stable item IDs. Removing them
makes the fixture represent the messy input the workflow will actually receive
rather than an idealized version, which is the point of the demo.

The capability is still wanted, so it moves to the roadmap as a preprocessing
step -- raw doc in, normalized ID'd structure out -- instead of an assumption
about the input. Roadmap also captures the HTML issue heatmap and the Playwright
UI-assessment track, and notes that the heatmap's spatial overlay depends on the
latter.

Flags one consequence worth knowing early: the disclaimer visibility condition
already in the baseline cannot be enforced without a browser, so part of v1.0 is
unverifiable until Playwright lands.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 9acc1ed — 2026-09-19 07:52

Lock confidentiality (Glean output never shown) and page representativeness

Glean output is GM-confidential and must never appear on screen or in the
repo -- describe it abstractly in narration only; the captured naive run
is Eric's own artifact and stands in as the on-screen example. Cadillac
page confirmed as one of several shapes she reviews (content
knowledge/experience type), not the whole set -- video should say so
precisely. Resolves repo/video hosting defaults (public GitHub repo, Loom).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### ba37c89 — 2026-09-19 07:52

Resolve repo and video hosting: private until done, direct upload

Repo stays private through iteration; goes public as a fresh, cleaned repo
as one of the last steps before recording, not upfront. Video is a local
file uploaded directly to the submission form, not hosted on Loom/YouTube.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### f26b1db — 2026-09-19 07:54

Merge branch 'main' into worktree-bridge-cse_017kaudW8RQKzdrh4XVH5Kuw


### 282c93a — 2026-09-19 07:55

Reconcile CLAUDE.md with the ID-removal pivot from main

Merged main's 'Remove stable IDs from baseline; add roadmap' work into this
branch. The design constraints assumed the ground-truth doc already had
stable IDs (4.6, 7.3.1); it deliberately no longer does, per ROADMAP.md item
1, so real messy PMM input is represented honestly. Reframed 2.1/2.2/2.3
around a normalization step that derives IDs from the raw doc as the
reviewer's own first stage, and replaced every numeric section reference
(10.1, 9.1, 4.3, etc.) with name-based references matching the current
ground-truth doc, which no longer numbers anything.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 7b6361e — 2026-09-19 08:22

Baseline v1.1: remove Open Items, seed three demo deltas

The v1.0 baseline was reconstructed from the live page, so running the
reviewer against that page returned all-PASS and demonstrated nothing.
v1.1 breaks that circularity on the baseline side rather than by building
a doctored HTML fixture, so both demo runs still execute against the real
URL.

Open Items removed — it was reviewer commentary, not approved copy, and
real PMM-authored ground truth documents do not carry it. Two knock-ons
handled deliberately:

- The tab-title quote still reads 2025, exactly as the page renders it.
  The model-year mismatch is no longer handed to the reviewer as a marked
  item; it must now derive the contradiction by cross-referencing four
  page-identity items that each individually match.
- The closed-world completeness assertion was relocated verbatim to its
  own section. It is the only thing in the doc that licenses flagging
  copy the page added, and paraphrasing it would have broken it.

Three seeded deltas, framed as a corporate copy update the agency has not
picked up: starting MSRP (easy), exterior finish order (medium), and an
added MSRP disclaimer exclusion (complex — an absence on the page, which
is the silent-miss class the incumbent tool fails at).

fixtures/ANSWER-KEY.md records every expected verdict and the traps that
must not fire, which makes a demo run scoreable instead of anecdotal.
CLAUDE.md reconciled in the same commit so no section still points at
Open Items or at page-side fixtures.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 6882fee — 2026-09-19 09:11

Baseline v1.2: strip to approved copy only, per PMM Word pass

Ported a hand-edited .docx back into the markdown source, which is the
repo invariant: the .md is edited, the .docx is regenerated from it. The
committed .docx is regenerated, not the uploaded Word file — text is
verbatim identical, Word's own styling is not preserved.

Every claims table, formatting rule, consistency-check table, the
completeness note and the revision history are gone. What survives is
boxed quotes, the two data tables, and the disclaimer's five numbered
conditions. That is closer to what the workflow actually receives: a
PMM's Word document is approved copy, not a reviewer's rulebook.

It also makes the reviewer's job harder in the way the real job is hard.
The traps are all still in the copy — "vs." in the H1 against "vs" in the
spec heading, uppercase HP/LB-FT in the table against lowercase lb-ft in
the narrative, two illustrative lists — but nothing now labels them as
intentional. A run that flags them is a reviewer defect, not a baseline
defect. Same for the medium seeded delta: with the "This exact order"
assertion deleted, the exterior finish order is enforced only by the
preamble's character-for-character rule.

One real loss, accepted rather than reversed: the completeness note was
the only closed-world assertion in the document, and without it the
reviewer has no licence to flag copy the page added.

All three seeded deltas and the 2025 tab title survived the Word pass
intact. Answer key and CLAUDE.md reconciled; no section still points at
a claims table or a sign-off marker that no longer exists.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 82d77c7 — 2026-09-19 09:16

Baseline v1.3: swap the medium delta for a claim-strength change

The exterior finish reorder is reverted — the baseline now matches the
page on that list again. In its place: the Introduction's heritage claim
reads "over two decades" in approved copy while the page still says
"nearly two decades."

Better separation across the ladder. The reorder was a permutation of
identical tokens; this is two different words that a model reads as
synonyms and that are not synonyms — one claims under 20 years of
V-Series engineering, the other over. V-Series launched in 2004, so
"over" is the accurate 2026 claim and the page is running stale copy,
which makes the cover story hold up and makes the finding a claim
substantiation problem rather than a typo.

It also exercises the paraphrase/near-match failure mode CLAUDE.md §4
predicts, which nothing else in the seeded set was testing. The three
deltas are now a changed number, a paraphrase-equivalent claim, and an
omission — three distinct classes rather than two flavours of one.

v1.2 deleted the bullet that used to spell out "not 'over two decades,'"
so nothing in the baseline points the reviewer at it.

Answer key and CLAUDE.md updated; the finish reorder moves to the unused
fallback menu in §5.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 9c02806 — 2026-09-20 07:48

Add page-capture fixtures and page-side structural defects

Baseline deltas (v1.1) cover copy Marketing changed that the agency has not
picked up. They cannot express defects in page structure, so this adds three
of those on the page side: a dropped Starting MSRP asterisk, the disclaimer
moved behind a <details> toggle, and an illustrative finish list rewritten as
exhaustive. The disclaimer's text is byte-identical in the seeded fixture, so
a text-only differ passes all three.

Both fixtures are committed captures rather than live fetches. Cloudflare 403s
curl and headless Chrome; capture.js gets through with headed Chrome on a
persistent profile. This also removes the last human step from Act 2 — the
2025/2026 model-year mismatch is visible directly in the committed capture.

Adds a !fixtures/*.html gitignore exception so the captures actually ship.
Reconciles CLAUDE.md section 5 and 7, and records in the answer key which
check classes the v1.2 Word pass made unenforceable, so future defects are not
seeded where the reviewer has no grounds to flag them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 8dd4677 — 2026-09-20 07:50

Start the build journal; require visibility in extraction

PROMPTS.md opens with iteration 0, the capture pipeline: a stale note said
headless Chrome was blocked, which I read as browser automation being blocked.
Headed Chrome on a persistent profile returned 200 and the full DOM first try,
which removed the human step Act 2 was about to depend on. Also logs the
process failure in the same session — recommending page-side fixtures without
checking whether a branch had already built the opposite approach.

Iteration 1 is reserved for the naive whole-document prompt, per section 4.

The visibility requirement is a real gap the fixtures exposed: text extraction
cannot tell "present" from "visible on load", so a string-comparing reviewer
would PASS disclaimer condition 5 against the seeded fixture where the text is
byte-identical but hidden behind a toggle. Section 3 now requires an
on_load_visible flag resolved by ancestor walk.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>


### 9ea31c1 — 2026-09-20 08:01

Log naive-run prompt and conditions before running it

Iteration 1 per CLAUDE.md section 4. The prompt, extraction choices, isolation
flags and one-run-per-fixture rule are committed ahead of any output so the
journal cannot be reconstructed after seeing results.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### b4cdb45 — 2026-09-20 08:03

Record naive-run results: it caught all three baseline deltas

Iteration 1, one run per fixture. The naive whole-document prompt caught
B1/B2/B3 on both fixtures plus the dropped asterisk and the exhaustive-list
rewrite, and hedged on the hidden disclaimer. CLAUDE.md and the answer key
predicted it would miss B2 and B3; that prediction did not hold and is now
annotated as such rather than left standing.

What the runs do show: no per-item coverage contract, a visibility assertion
made without basis on one run and correctly withheld on the other, the
model-year mismatch surfaced but attributed to the ground truth, and output
that is not pasteable to an agency.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 5831ae3 — 2026-09-20 08:18

Add fresh capture and a faithful baseline extracted from it

The v1.0 baseline was built partly from the 2025 Wayback capture and partly
from WebFetch reads of the live page, and v1.1 deleted the Provenance note
that said so. This recaptures the live page with headed Chrome and generates
a new baseline directly from the raw DOM, so no boxed quote is retyped.

The generator aborts if the page's block structure changes. Output was
checked two ways: all 15 boxed quotes appear verbatim in both captures under
a different extractor, and a diff against v1.3 shows exactly the three seeded
deltas plus the capture date and source line, nothing else.

The baseline keeps the page's curly apostrophes, so the apostrophe trap does
not fire against it; v1.3 still exercises it. By construction the pristine
capture passes it in full, so it is a reference rather than a demo input.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 3ba391e — 2026-09-20 08:21

Correct two claims about the fresh baseline; add Run C

Both were caught in review and are logged as their own correction in
PROMPTS.md rather than silently amended.

The verification of boxed quotes reported 15/15 but tested 14: an
operator-precedence slip in the check ("a or b and False" reduces to "a")
skipped the one quote containing an entity, while the denominator still said
15. It also never checked the spec table. Re-run properly: 14/14 prose quotes,
3/3 header cells and 21/21 table cells in order, on both captures.

The claim that the pristine capture passes the faithful baseline "in full" was
wrong. The baseline records the tab title and the H1 verbatim and they
contradict each other, so the expected result is zero FAIL and one OPEN -
PAGE INCONSISTENT, not all-PASS. That makes this pairing the strongest Act 2:
a baseline extracted from the page by script, against which the tool still
surfaces a real defect. Adds it to the answer key as Run C, and states in
CLAUDE.md which of the two baselines is which.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### f88e0a2 — 2026-09-20 10:43

Reset: drop seeded v1.3 baseline; port copy defects page-side

The seeded baseline pointed the fault the wrong way (approved copy edited to
disagree with the page) and the original baseline's provenance rested partly
on a 2025 Wayback capture and a summarizing model. The faithful,
script-extracted baseline now takes the canonical filename, and v1.3 is
removed (recoverable from git).

The three copy defects it carried are ported into the page as P4-P6 so the
defect class the PMM actually reviews is kept and fault points the right way.
The faithful baseline already lacks dealer-installed accessories, so P6 drops
dealer fees instead. The rebuild fixture now carries six defects.

Iteration 1's naive outputs move to fixtures/superseded/ since they were
produced against a baseline no longer at HEAD; the journal entry is left
unedited and iteration 2 records the reversal. CLAUDE.md, the answer key,
README and ROADMAP are rewritten to describe the current design. Iteration 2
also fixes the scoring rubric and the on-camera-run rule before any output.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 9a8142a — 2026-09-20 10:44

Add batch runner for the N-run naive measurement

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 305025b — 2026-09-20 10:49

Record the N=5 naive measurement: every text-visible defect caught

Ten runs, five per fixture, scored against a rubric committed before any
output existed. The naive whole-document prompt caught all five text-visible
defects in all five runs on the rebuild (25 of 25 instances) and raised no
false positives on either fixture. It hedged on the hidden-disclaimer defect
in 5 of 5, and asserted "visible on load" as a pass on the pristine page in 4
of 5.

This does not reproduce the silent-miss failure CLAUDE.md was written to
expect, and the journal and CLAUDE.md now say so. Act 1 rests on what the
outputs lack: no coverage count in any of ten, a visibility question that
turns on the literal words "Read more", section names and severities that vary
run to run, and no verdict for a page that contradicts itself.

Run 1 of each fixture becomes the on-camera artifact per the rule fixed
beforehand. All ten are kept.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 85f4b0d — 2026-09-20 10:56

Apply the PMM's Word edits to the baseline; delete the N=5 naive runs

Eric edited the ground truth in Word. A strict diff against the committed
baseline shows two deletions and nothing else: the Source capture header line
and the Premium Options and Packages section. The generator is updated to stop
emitting both, the .md and .docx are regenerated, and the regenerated .docx is
text-identical to his file, paragraph for paragraph.

The Premium Options table was the only source of OPEN - NEEDS MARKETING, so
CLAUDE.md and the answer key now say that verdict has no live example in the
Cadillac fixtures rather than pointing at a table that is gone.

Deletes the ten naive-run outputs and the two canonical copies of run 1, at
Eric's direction; recoverable at 305025b. The copies also could not be
reproduced against the edited baseline. CLAUDE.md sections 4 and 5 no longer
cite the deleted runs, and the journal records the deletion as iteration 3
instead of rewriting iteration 2.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 957ba4f — 2026-09-20 11:19

Remove the batch runner for the deleted naive-run measurement

It wrote to fixtures/naive-runs/, which no longer exists, and nothing else
references it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 10eeb1b — 2026-09-20 11:36

Reset the build journal at the end of initialization

PROMPTS.md restarts at iteration 1, the naive whole-document prompt, per
CLAUDE.md section 4. The initialization-period journal (iterations 0 to 3:
capture pipeline, baseline provenance, the seeded-baseline reversal, the naive
measurement and its deletion) is recoverable from git at 957ba4f.

CLAUDE.md and the answer key referenced specific iterations of the old journal;
those now point at the commit instead of at entries that no longer exist.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 4aa0fd8 — 2026-09-21 08:22

Add ideation: Glean vs. Claude Code options for the ground-truth review

Two ranked idea sets (stay in Glean, port to Claude Code) grounded in the
repo's coverage-contract constraints and the Glean agent's two failure modes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 320c8ca — 2026-09-21 08:34

Add requirements-only plan for the QA reviewer coverage pipeline

Covers intake with a count guard, page capture with visibility and
geometry, per-item verdicts with a hard error on any gap, a single
findings record, round-over-round diff with a footnote for baseline
edits, and an annotated real-page overlay.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 678b349 — 2026-09-21 08:54

Apply document-review findings to the QA reviewer requirements plan

Confirmation lists every checklist item with source text, round diff
reuses verdicts and flags verdict-only changes, not-found items reach the
agency block, snapshots are self-contained renders, judgment quotes must
match page nodes, visibility gains an undetermined state, cross-item
consistency checks become checklist items, and an edited-baseline fixture
is added for the footnote flow.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### b889b3a — 2026-09-21 09:15

Enrich the QA reviewer plan to implementation-ready

Adds the Planning Contract (13 key technical decisions), ten implementation
units, verification gates and definition of done, resolves the requirements
plan's outstanding questions, and applies the headless review's safe fixes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### eb9a256 — 2026-09-21 09:29

Apply the plan review's proposed fixes

Single finding-number sequence for badges, page-keyed run storage,
network-blocked snapshot renders with a fetch policy, header-row and text
block definitions, frozen confirmed checklist, escaped HTML report,
replaced-ID surface in the round diff, and vendored fixtures as scored inputs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>



---

## Appendix B — commit log for this session's own work

Full chronological commit messages, `7b303c6` onward: the recovery/restore, then the fix
commits for the six-lens code review (Groups 1-4, the testing lens). Cross-reference against
the numbered prompts above -- each commit's timing lines up with the prompt that prompted it.

### 7b303c6 — 2026-09-22 01:19

Restore qa_review implementation from a recovered patch

Recovers the ce-work stage (qa_review/ package, tests, the qa-review
skill, and the PROMPTS.md journal through iteration 3) that was lost
along with its git history. Applied cleanly on top of eb9a256 (the
implementation-ready plan) and re-verified: 152/152 tests pass after
regenerating the two vendored fixture snapshots, which weren't part
of the recovered patch and are reproducible from the committed page
captures via `qa_review vendor`.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 8d467e8 — 2026-09-22 01:29

Harden qa_review clean against an unvalidated --runs/--profile path

clean --all-runs and clean --profile did shutil.rmtree(path, ignore_errors=True)
on whatever --runs/$QA_REVIEW_RUNS or $QA_REVIEW_PROFILE resolved to, with no
check that the path was actually a qa_review store. A misconfigured env var
pointed at $HOME (or any unrelated directory) would silently delete it.

Adds two guards before either rmtree: a hard refusal for paths that resolve to
the user's home directory or a filesystem root, and a store-shape check (only
recurse into directories that look like our own runs/confirmations layout).
The browser profile directory now writes a marker file on creation so clean
can tell "ours" from "some other directory" instead of guessing from contents.
Also drops ignore_errors=True so a real failure is reported instead of hidden,
and the --all-runs success message now says confirmations are cleared too
(agent-native P3).

Security P2 and agent-native P3 findings from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 5a0ab0b — 2026-09-22 01:30

Add a subprocess timeout to model calls

ClaudeCLIModel.ask had no timeout on the claude -p subprocess call, so a
hung model call blocked the run forever instead of failing after its
retry -- there was no route back to ModelCallError. Adds a timeout
(QA_REVIEW_MODEL_TIMEOUT, default 180s), and a subprocess.TimeoutExpired
now counts as a failed attempt like a nonzero exit, so it retries once
and then raises ModelCallError naming the timeout.

SKILL.md step 3 now says review can take several minutes and to run it
with a long Bash timeout or in the background, since an agent using the
default two-minute Bash timeout could otherwise kill it mid-run and
orphan the run dir.

Agent-native P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 41686e3 — 2026-09-22 01:32

Turn capture/IO failures into reported errors, not tracebacks

A missing baseline file, a missing Chrome, a Playwright timeout, or the
claude binary not being on PATH all previously died as an unhandled
Python traceback with exit 1 -- the same code as "coverage contract
broken" -- so an agent following the skill couldn't tell an environment
problem from an actual review failure. A failed capture also left
runs/<key>/<stamp>/ behind, possibly holding a confidential page
snapshot, since cleanup only ran for CoverageError/ModelCallError.

- cmd_intake/cmd_confirm/cmd_review now catch a missing/unreadable
  baseline and report it plainly at exit 2, instead of raising OSError
  from inside file_hash().
- cmd_review widens its except clause to also catch OSError and
  playwright's Error (imported lazily), cleans up the run dir the same
  as a coverage error, and exits 3 -- a code of its own so an agent can
  tell "the page is broken" from "the environment is broken".
- ClaudeCLIModel.ask wraps a missing claude binary (FileNotFoundError)
  into ModelCallError instead of retrying pointlessly or crashing.
- SKILL.md documents the exit codes (0/1/2/3) and step 3's expected
  runtime.

Agent-native P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### f20851c — 2026-09-22 01:33

Signal degraded visibility checks on stdout, not just the report header

render.py already noted "page styles were not vendored (visibility and
overlay degraded)" in the report header, but cmd_review printed only
the coverage line and file paths on success and exited 0. An agent
following the skill could show a disclaimer-visibility PASS as reliable
without ever seeing that the check ran degraded.

cmd_review now prints a warning to stderr (plus any capture notes) when
cap["styles_vendored"] is false. SKILL.md tells the agent to say so up
front and not present visibility verdicts or the annotated screenshot
as reliable when that warning (or the same line in the report header)
is present.

Agent-native P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### f35aa3c — 2026-09-22 01:36

Cite the baseline ID in the agency block; catch subject-less conditions at intake

Two small P3s from the six-lens review:

- render_agency_block printed a running number and verdict but no baseline
  ID, so a FAIL couldn't be traced back to the baseline without the report
  table. CLAUDE.md sec 2.2/2.7 require every finding to cite its ID.
  Regenerated tests/golden/agency-rebuild.txt to match.

- A structural (visibility) condition the model typed with no subjects
  named surfaced as an agency-facing "NOT FOUND ON PAGE", blaming the
  agency for what's actually an intake defect. build_checklist now raises
  IntakeError for this case, so it's caught before the PMM ever confirms
  the checklist.

Correctness P3 and project-standards P3 findings from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 9d9b42d — 2026-09-22 01:38

Stop reviewing a bot-protection challenge as if it were the real page

SKILL.md promised a kept login so gated staging sites work, but nothing
established that login: _wait_past_challenge polled for 20 seconds and
then fell through regardless of outcome, so a login page or CAPTCHA
interstitial got captured and reviewed like a normal page -- exit 0, a
confident-looking report of mostly NOT FOUND ON PAGE, no warning that
it reviewed the wrong page.

_wait_past_challenge now raises CaptureError when the title still
matches the challenge pattern after the wait, which flows through
cmd_review's widened except clause (exit 3, same as other environment
failures) instead of quietly producing a wrong report.

Adds `qa login <url>`, which opens the persistent browser profile
headed and waits for the user to finish logging in, so there's an
actual way to establish the session the skill already claimed existed.
SKILL.md tells the agent to ask the user to run it once for gated
sites, and to fall back to a saved .html file when there's no display.

Agent-native P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 3a14afa — 2026-09-22 01:39

Document why OPEN -- NEEDS MARKETING stays unreachable for now

The six-lens review flagged that judge_item's rules never offer the
model OPEN -- NEEDS MARKETING, even though it's declared in schema.py's
verdict taxonomy per CLAUDE.md sec 2.4. The finding itself calls this
advisory rather than a defect: the Cadillac baseline has no unsigned
item to write and check the rule against (the Premium Options table
that used to supply one was removed in the PMM's Word pass, per CLAUDE.md
sec 2.4), so implementing it now would be unverifiable against any real
example. Left unreachable, with the reasoning recorded in judge.py and
PROMPTS.md instead of forcing a rule nothing can check.

Project-standards P2 finding from the six-lens code review -- resolved
as documented-and-deferred rather than code changed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 9cc21e0 — 2026-09-22 01:50

Fix stale PASS reuse and misattributed quotes in judgment items

Two P1/P2 findings from the adversarial and correctness lenses, both
in the judgment-reuse path:

- reuse_prior only compared the blocks a prior verdict's quote actually
  cited, not every candidate block the model was shown. A whole-page or
  consistency PASS that cited one block would survive a change in any
  OTHER candidate block untouched -- e.g. a consistency check citing
  only the H1 would keep reusing PASS across a round where the tab
  title regressed, since the title was shown to the model but never
  quoted. Reproduced with StubModel: a two-block consistency candidate
  set, only one block cited, the other regressed -- old code reused
  PASS with zero model calls.

  Finding now carries `basis`: the normalized text of every candidate
  block shown to the model, not just the cited ones. reuse_prior now
  requires the full basis unchanged, falling back to cited-only for
  records written before this field existed.

- _owner resolved a quote by scanning ALL page blocks in page order,
  not the candidates the model was actually shown. A quote that also
  happened to appear in an earlier, unrelated block (e.g. the tab
  title) was attributed to that block instead of the real candidate,
  so its overlay location, evidence hash and reuse key tracked the
  wrong text -- and two distinct-block quotes both matching in the
  title could collapse to one block, turning a real inconsistency into
  NOT FOUND ON PAGE. _owner now checks candidates first, falling back
  to the full block list only if none matches.

Verified both new tests fail against the pre-fix code (git stash) and
pass against the fix.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 6feaa38 — 2026-09-22 01:58

Fix verbatim matching: decoy fragments, glued marks, and shifted table indices

Four findings from the adversarial/correctness lenses, all in check_verbatim:

- A table-cell locator with no matching page cell (a deleted row/column)
  fell through to a whole-page token-span search, so the approved value
  passed if it appeared ANYWHERE -- a different table, a hidden block, the
  title. Reproduced: a deleted trunk-cargo row still PASSed against an
  unrelated sentence containing the same figure. Now NOT FOUND ON PAGE
  when the locator has no cell at all, instead of falling through.

- When the located cell's text differed, it FAILed unconditionally. The
  page's table index counts every <table> in the DOM; the baseline's
  counts only approved-doc tables, so an unrelated table earlier on the
  page shifts every subsequent index -- the true match can legitimately
  sit at the same row/col under a different table number. Now checks
  that position before failing, and WARNs (not PASS -- this is still
  worth a look) when found there.

- A whole-token-span match anywhere on the page PASSed regardless of
  which block it was in, so an approved H1 quote still matched via the
  page's <title> (or a hidden block) even after the real H1 was altered
  -- the reviewer cited the decoy and missed the actual defect. A
  span-only match (not an exact whole-block match) now WARNs when its
  only hit is the title or a hidden block, instead of passing silently.
  (Tried a broader "does some other block nearly match instead"
  heuristic first; it false-positived on the real Cadillac fixture,
  where title/breadcrumb/H1 legitimately repeat overlapping phrasing --
  dropped in favor of the narrower, precise kind/visibility check.)

- The whole-token-span boundary check only rejected an alphanumeric
  neighbour, so an added footnote mark or a decimal continuation passed
  through unchanged: "$57,600" matched inside "$57,600.99", "Starting
  MSRP" inside "Starting MSRP*", "Heads-Up Display" inside "Heads-Up
  Display†". The boundary check now also rejects a footnote/qualifier
  mark or punctuation that continues into a digit.

All new tests verified to fail against the pre-fix code (git stash) and
pass against the fix; the full suite, including the real-page fixture
tests, stays green (182 passed).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 7c121d5 — 2026-09-22 02:03

Prefer a visible block over a hidden decoy when citing a duplicate match

When approved text appears in more than one block -- a hidden print-only
or aria-hidden duplicate ahead of the real visible copy, in DOM/page
order -- check_verbatim cited whichever came first regardless of
visibility. A structural (visible-on-load) condition reading that cited
block would then FAIL a disclaimer that is actually visible: a false
accusation, since the reverse case (citing a visible block when only a
hidden one truly exists) can't hide a real defect.

Whole-match candidates are now sorted visible-before-undetermined-before-
hidden (a stable sort, so occurrence indexing among equally-visible
blocks is unchanged) before picking the occurrence-th hit.

Correctness P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### a252f82 — 2026-09-22 02:06

Never let an empty or unresolved review read as "found no differences"

Two related P2 findings from the correctness and adversarial lenses:

- A baseline with no boxed quotes, table cells or numbered conditions
  produced an empty-but-"successful" Checklist (guard.applicable=False),
  and review ran to a vacuous "0/0 checked" clean report -- the coverage
  contract is trivially satisfied by having nothing to check. build_checklist
  now raises IntakeError ("nothing to review") instead, and run_review
  raises CoverageError as a second layer if it's ever handed an empty
  item list directly. (CLAUDE.md's history already called this the
  intended fix; the recovered patch predated it.)

- Separately, a review where every non-PASS finding was a check-by-eye
  WARN (e.g. visibility undetermined because styles weren't vendored) or
  an OPEN item had zero agency-facing rows -- and render_agency_block
  said "found no differences" anyway. That's the pasteable block, so an
  unresolved review became an affirmative clean bill to send the agency.
  It now says how many items still need a look or are open for Marketing
  instead, and only says "no differences" when the review is genuinely
  clean.

Verified all three new tests fail against the pre-fix code (git stash)
and pass against the fix.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### e37487c — 2026-09-22 02:09

Bind confirmation to checklist content, not just the baseline's hash

confirmed.json stored only the baseline file's hash, and checklist.json
is overwritten whenever that hash changes. The gap: edit the baseline
(hash B, checklist.json rewritten), then revert to the confirmed content
(hash A) -- intake sees a hash mismatch and reruns the model, and the
freshly regenerated checklist (a condition's type, subjects or a
consistency proposal can come out differently on a second model call)
gets written under hash A again. is_confirmed(folder, A) was still True,
so `intake` printed "This checklist is confirmed." and `review` proceeded
without the PMM ever seeing the regenerated checklist.

confirm() now stamps a content hash (sha256 of the frozen checklist's
own JSON) alongside the baseline hash, and is_confirmed() takes the
Checklist itself and requires both to match. A checklist regenerated
from the same baseline text is only "confirmed" if its content is
byte-identical to what was actually confirmed.

Adversarial P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### e387448 — 2026-09-22 02:11

Show model-chosen subjects and consistency refs in the confirm view

The intake model decides which item(s) a structural condition binds to
and which items a consistency check compares -- and check_structural
then PASSes whenever those bound blocks are visible, whatever the
condition text actually says. Point condition 5 at the wrong boxed
quote, or omit one of two items from a consistency check's refs, and
the PMM had no way to catch it: render_view printed only `id, type,
first 8 words`, never the subjects, refs or label the model chose.

A structural or judgment item now shows "about: <gist of each subject's
text>", and a consistency item shows "'<label>' across: <gist of each
ref's text>", so the thing the PMM is actually confirming -- the
model's binding choice, not just the condition's wording -- is visible
before she signs off.

Left out the finding's other suggestion (validate that a subject's text
"overlaps" the condition text, e.g. checking for the word "disclaimer")
as a fragile heuristic prone to false rejections on legitimate baselines;
visibility for a human reviewer is the safer fix for a judgment call
this open-ended.

Adversarial P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 056117d — 2026-09-22 02:16

Fail markdown intake loudly on unrecognized structure instead of dropping it

read_markdown only recognized boxed quotes and numbered conditions in
one exact, flush-left form, and raw_counts_markdown re-counted the same
grammar -- so anything that didn't match (an indented '> quote', a `2)`
paren-numbered or indented condition, a wrapped second line of a
hand-typed or pandoc-wrapped condition, a bulleted list or code fence)
vanished with no error, and the count guard agreed with the extractor
because it was blind to the same lines. A checklist missing an item
still reports full coverage -- the exact failure mode the coverage
contract exists to prevent, just one layer up in intake instead of in
the review itself.

Now:
- A condition's wrapped continuation lines (no special prefix,
  immediately following an open condition, ending at a blank line or
  the next structural element) are folded into its text instead of
  silently dropped.
- An indented quote, a paren- or indented-numbered condition, or a
  bulleted list/code fence raises IntakeError naming the line, instead
  of disappearing.

Verified against the real committed baseline and the reuse fixture (no
behavior change there -- neither uses any of these forms) and against
six new regression tests, all confirmed to fail on the pre-fix parser
via git stash.

Adversarial P2 finding from the six-lens code review. This closes out
the "intake and confirmation integrity" group.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 95fc058 — 2026-09-22 05:56

Fix the docx count guard's blindness to Word's own attribute-bearing XML

raw_counts's "independent second pass" only matched bare tags -- <w:p>,
<w:tr>, <w:tc>, an unattributed <w:pBdr><w:left> pair. Word round-trips
a PMM's file with w:rsidR/w:rsidRDefault attributes on nearly every
element, so a real Word-saved baseline made this second pass count 0
while read_docx's proper XML parsing correctly extracted the items.
applicable then came out False, intake skipped the count-guard
comparison entirely, and the checklist view told the PMM "no boxed
quotes, table cells or numbered conditions were found" -- a guard that
can't see its own source verifies nothing, on the one baseline type
(Word) this is all for.

Every tag is now matched by its start (<w:p\b, <w:tr\b, <w:tc\b,
<w:pBdr\b ... <w:left\b) rather than requiring an exact, attribute-free
open tag. build_checklist also now treats "extraction found real items
but the raw pass found none" as an IntakeError rather than "not
applicable" -- defense in depth against the next guard blind spot,
wherever it turns out to be.

Verified against a hand-built attribute-bearing .docx (md2docx.py's own
output never carries rsid attributes, so the existing fixtures never
exercised this) and against the pre-fix code via git stash.

Adversarial P1 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### c0d76dc — 2026-09-22 05:59

Stop trusting vendored CSS that silently lost rules, and fix a CSS injection

Two findings, both in vendor_html:

- A failed @import (nested inside a successfully-fetched <link> sheet,
  or inside an inline <style> block this pass never even looks at) was
  silently dropped -- an empty string, ok left True, no note. Visibility
  is computed by re-rendering this vendored snapshot, so a dropped rule
  can be the exact one that hides a disclaimer (an accordion collapse,
  a tooltip): condition 5 ("visible on page load") would PASS against a
  snapshot missing the rule that hides it on the real page. Both cases
  now append a note and set ok=False.

- The </style escape was case-sensitive ("</style" only), so fetched
  CSS -- attacker-controlled: any host that passes the fetch policy --
  containing "</STYLE><script>...</script>" closed the tag early and
  ran a live script in the offline render, whose DOM and screenshot are
  trusted for every verdict. Reproduced and fixed with a case-insensitive
  substitution; also neutralizes "<!--" the same way.

Verified against the real Cadillac fixtures (unaffected -- no import
failures or inline @import there) and against the pre-fix code via git
stash for all three new tests.

Adversarial P1 and security P2 findings from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 517ffc6 — 2026-09-22 06:03

Check every redirect hop before requesting it, not just the final URL

_browser_fetch let Playwright auto-follow redirects (max_redirects=3)
before the fetch policy ever saw the intermediate hops -- check_url ran
only on the starting URL and the final one. A public URL that 302s to
http://127.0.0.1:PORT/... or a cloud metadata address reached that
internal service before the policy discarded the response: a blind
SSRF, since the request itself already happened.

fetch() now requests with max_redirects=0 and follows Location headers
manually, checking each hop against the policy before it's requested
(up to 3 hops, matching the old cap).

Also fixed _blocked(): the enumerated is_private/is_loopback/... flags
don't cover 100.64.0.0/10 (CGNAT, Tailscale) -- verified _blocked("100.64.0.1")
was False. Switched to `not a.is_global`, which covers that and any other
gap in the enumerated list, with an explicit is_multicast check kept
alongside it since ipaddress.is_global counts some multicast ranges as
"global".

Verified with a fake Playwright request client (IP-literal URLs
throughout, so the tests never depend on real DNS) against both the
fix and the pre-fix code via git stash.

Security P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 25d80a8 — 2026-09-22 06:07

Close regex-stripper bypasses and add a CSP as a structural backstop

Regex is not an HTML parser, and three real bypasses on the saved-file
path proved it: "<svg/onload=...>" (a "/" before an attribute name is
whitespace to a real tokenizer, not just a self-close marker), a
closing tag carrying its own bogus attributes ("</script foo>" still
closes the tag to a browser but not to "</script\s*>"), and an
unclosed "<iframe src=...>" with no matching close for a paired-tag
pattern to strip. All three survived unchanged and this snapshot's
DOM and screenshot are what every verdict trusts.

Fixed the three specific patterns, but regex sanitization can't be made
airtight this way -- the module's own docstring calls the result
"inert", which only a real enforcement mechanism backs up. vendor_html
now also injects a CSP meta tag (default-src 'none'; style-src
'unsafe-inline'; img-src/font-src data:) into the snapshot, blocking
any script or frame that slips past the regex regardless. Verified
against the real Cadillac fixtures and the full browser-based test
suite (page.evaluate() extraction, visibility, overlay, screenshot,
end-to-end review) that the CSP doesn't break rendering, extraction or
screenshots -- Playwright's evaluate runs via CDP, outside the page's
own CSP enforcement.

Security P2 finding from the six-lens code review. This closes out the
"vendoring and fetch-policy hardening" group.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### d8a5c90 — 2026-09-22 06:12

Golden test can no longer pass by silently creating its own answer; add missing consistency test

- check_golden wrote the expected file whenever it was missing, then
  compared the output to itself -- deleting or forgetting to commit a
  golden turned the test green instead of failing, and running with
  UPDATE_GOLDEN set (or from a checkout missing the file) silently
  rewrote tracked files. It now only writes under UPDATE_GOLDEN=1;
  otherwise a missing golden fails the test by name.

- judge_item's single-block INCONSISTENT downgrade (two valid, distinct
  quotes that both resolve to the same block, so the model quoted
  itself rather than showing two blocks disagree) had no test.
  ConsistencyTests covered two-block INCONSISTENT, an invented quote,
  and PASS, but not this one -- the exact rule the model-year mismatch
  (this project's hero finding) depends on being enforced.

Testing P3 findings from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### cc53bc3 — 2026-09-22 06:14

Disambiguate identical condition wording; test the real duplicate-ID path

Verbatim items already got an ordinal suffix for identical text within
a section (item_id(..., n)); condition IDs never did, so two conditions
repeating the same wording in one section collided on a single ID.
run_review would then correctly reject the whole checklist as a
coverage-contract violation -- but for a document that has nothing
wrong with it, just a hand-typed baseline repeating a line. Condition
IDs now track the same per-(section, text) ordinal counter.

test_duplicate_verdict_raises proved only that the error message
exists: it patched runner._collect, a function whose only purpose was
being a seam for this one test. Replaced it with a real checklist
containing two items that share an ID, which removing _collect (now
dead code) doesn't change -- run_review's actual duplicate detection
already handles this without any hook.

Testing P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### bd21a04 — 2026-09-22 06:16

Strengthen the currency-candidate test to actually exercise the price branch

BLOCKS has only 4 elements, and _candidates falls back to the top 5
by similarity when nothing else is kept -- so all 4 blocks, including
the price block, reached the prompt whether or not the price-block-
inclusion branch (_PRICEY/_CURRENCY matching) ran at all. Verified:
disabling _PRICEY left the test green.

Now uses 8 blocks, 7 of them deliberately dissimilar to the item text
(similarity 0.0, confirmed), so the price block only reaches the
prompt via the price branch -- and asserts the unrelated filler blocks
are absent, which only holds if that branch short-circuits the
similarity fallback as designed. Also adds the previously-untested
fallback path itself: with no currency block, candidates cap at the
top 5 by similarity, not all 8.

Testing P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 181c67b — 2026-09-22 06:18

Strengthen the --prior test to actually distinguish it from the default

The old test reviewed the same static page three times, so every
candidate prior (named, default, or --prior silently ignored) produced
the same "## Since the last round" diff -- verified: patching
store.find_prior to discard override left the test green. If --prior
broke, the PMM would silently get a diff against the wrong round.

Round 2's capture now mutates one block ("Buy now" -> "Buy today"), so
diffing round 3 against the named --prior (round 1, identical) versus
the default most-recent (round 2, which regressed) are provably
different outcomes. The rewritten test asserts round 3's report shows
no "Fixed" entry and "items unchanged and passing" -- which only holds
if --prior actually selected round 1. Caught my own first draft of this
test failing to distinguish the two cases before landing this version.

Testing P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 0a8a440 — 2026-09-22 06:20

Add CLI-level tests for intake and review failure paths

AE6 (a source with a dropped item "stops before reviewing") was only
tested against build_checklist directly; nothing checked that cmd_intake
actually reports the error, exits 2, and writes no checklist.json --
which matters because a later confirm/review depends on that file's
absence to correctly keep refusing. Likewise cmd_review's ModelCallError
branch (delete the run dir, exit 1, no partial report) was never
exercised: only CoverageError was, so a regression that left a partial
run folder behind, or a frozen checklist that failed the guard, would
have looked like a valid prior round or a confirmable checklist to
anyone glancing at the runs directory.

The model-error test needed a baseline with a judgment condition --
page-baseline.md has none, so review never calls the model for it at
all -- so it uses MINI with a model that answers intake normally and
then raises ModelCallError for anything else.

Testing P2 finding from the six-lens code review.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### 1b117ec — 2026-09-22 06:21

Verify the overlay actually draws badges, not just plans to

Every existing overlay assertion checked out["placed"], which
build_overlay computes from the findings record before rendering --
none of them looked at the DOM the INJECT script actually produces, or
compared the annotated screenshot to an unannotated one. If the
injected script drew nothing, drew badges for the wrong blocks, or drew
one for a NOT FOUND finding, every overlay test would still pass.
Verified: replacing INJECT with a no-op left every existing test green.

Two new tests: re-running the same INJECT script and inspecting the
resulting DOM directly (marker count matches placed findings, their
labels match, and the NOT FOUND finding never gets one), and comparing
the annotated screenshot's bytes against a plain render of the same
snapshot to confirm the overlay visibly changed something.

Testing P2 finding from the six-lens code review. This closes out the
testing lens.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>


### Session log entry -- 2026-09-22T13:19:09Z

> anythign left to commit push merge?

**What happened:** _(auto-logged by the UserPromptSubmit hook; not yet annotated)_

---

### Session log entry -- 2026-09-23T03:56:40Z

> requirement for my submission is to include a link to my github. 
> 
> let's do a few checks:
> 
> 1. is there any private information in this repo that wouldn't be wise to leak out? tokens, references to me, proprietary GM things?
> 2. if you were to create a sanitized version of this github, what would the whole filetree look like? I want to inspect the files you'd want to create as a public facing one
> 3. what are tradeoffs to if i just set the current repo to public for the time being?

**What happened:** _(auto-logged by the UserPromptSubmit hook; not yet annotated)_

---

### Session log entry -- 2026-09-23T04:00:50Z

> build the sanitized repo and let me inspect it before pushing

**What happened:** _(auto-logged by the UserPromptSubmit hook; not yet annotated)_

---

### Session log entry -- 2026-09-23T04:03:30Z

> include session-prompts.md
> 
> ignore fixtures/naive-run-output

**What happened:** _(auto-logged by the UserPromptSubmit hook; not yet annotated)_

---
