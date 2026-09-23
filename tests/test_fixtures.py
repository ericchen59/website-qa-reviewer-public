"""The seeded fixtures against fixtures/ANSWER-KEY.md, with a stubbed model (no live calls).

Verbatim and structural verdicts are deterministic, so they can be scored exactly. The model
answers (judgment items and the consistency check) are stubbed with valid quotes.
"""

import pathlib
import tempfile
import unittest

from qa_review.diff import diff_records
from qa_review.intake import build_checklist
from qa_review.model import StubModel
from qa_review.render import assign_numbers, render_agency_block, render_report
from qa_review.runner import run_review
from qa_review.schema import FindingsRecord
from tests.support import BASELINE, ROOT, intake_stub
from tests.test_visibility import BROWSER

FIX = ROOT / "fixtures"
EDITED = FIX / "GROUND-TRUTH_ct5v-edited-intro.md"


class JudgeStub(StubModel):
    """Valid-quote answers: every judgment PASSes, the year check finds the tab-title mismatch."""

    def __init__(self):
        super().__init__({})

    def ask(self, prompt, schema, label):
        if "quotes" in schema["properties"]:
            return {"verdict": "INCONSISTENT", "reason": "2025 vs 2026",
                    "quotes": ["2026 CT5-V vs. 2025 CT5-V Blackwing Comparison | Crestmont Cadillac",
                               "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}
        return {"verdict": "PASS", "quote": "Dealer sets final price.", "reason": "stub"}


def checklist(path=BASELINE):
    return build_checklist(path, intake_stub(structural_index=4, consistency_marker="Blackwing Comparison"))


def review(cl, blocks):
    return run_review(cl.items, blocks, JudgeStub())


def failing_texts(res, cl):
    by = {i.id: i for i in cl.items}
    return sorted(by[f.item_id].text for f in res.findings if f.verdict == "FAIL")


@unittest.skipUnless(BROWSER, "Playwright and Chrome are required")
class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qa_review.capture import capture
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.cap = {name: capture(str(FIX / f), cls.tmp / name)
                   for name, f in (("rebuild_v", "agency-rebuild-vendored-2026-09-20.html"),
                                   ("pristine_v", "live-2026-09-20-vendored.html"),
                                   ("rebuild", "agency-rebuild-2026-09-20.html"),
                                   ("pristine", "live-2026-09-20.html"))}
        cls.cl = checklist()

    def test_vendored_snapshots_are_self_contained(self):
        self.assertTrue(self.cap["rebuild_v"]["styles_vendored"])
        self.assertTrue(self.cap["pristine_v"]["styles_vendored"])
        self.assertFalse(self.cap["rebuild"]["styles_vendored"])

    def test_rebuild_fails_exactly_the_six_seeded_defects(self):
        res = review(self.cl, self.cap["rebuild_v"]["blocks"])
        texts = failing_texts(res, self.cl)
        self.assertEqual(len(texts), 6, texts)
        for needle in ("nearly two decades", "$57,600", "Starting MSRP*", "finishes that include", "dealer fees",
                       "visible text on page load"):
            self.assertTrue(any(needle in t for t in texts), needle)

    def test_the_hidden_disclaimer_is_caught_by_visibility_not_string_comparison(self):    # P2 / AE2
        res = review(self.cl, self.cap["rebuild_v"]["blocks"])
        by = {i.id: i for i in self.cl.items}
        cond5 = next(f for f in res.findings if by[f.item_id].type == "structural")
        self.assertEqual(cond5.verdict, "FAIL")
        pristine = review(self.cl, self.cap["pristine_v"]["blocks"])
        self.assertEqual(next(f for f in pristine.findings if by[f.item_id].type == "structural").verdict, "PASS")

    def test_pristine_has_zero_fail_and_one_open(self):
        res = review(self.cl, self.cap["pristine_v"]["blocks"])
        c = FindingsRecord(run_id="r", baseline={}, page={}, findings=res.findings).counts()
        self.assertEqual((c["FAIL"], c["WARN"], c["NOT FOUND ON PAGE"]), (0, 0, 0))
        self.assertEqual(c["OPEN — PAGE INCONSISTENT"], 1)

    def test_every_run_has_one_verdict_per_checklist_item(self):
        for name in ("rebuild_v", "pristine_v", "rebuild", "pristine"):
            res = review(self.cl, self.cap[name]["blocks"])
            self.assertEqual([f.item_id for f in res.findings], [i.id for i in self.cl.items], name)

    def test_unvendored_originals_pass_the_verdict_checks_with_visibility_undetermined(self):
        res = review(self.cl, self.cap["pristine"]["blocks"])
        by = {i.id: i for i in self.cl.items}
        cond5 = next(f for f in res.findings if by[f.item_id].type == "structural")
        self.assertEqual((cond5.verdict, cond5.check_by_eye), ("WARN", True))
        rebuild = review(self.cl, self.cap["rebuild"]["blocks"])
        self.assertEqual(len(failing_texts(rebuild, self.cl)), 6)

    def test_round_two_under_the_edited_baseline_marks_the_replaced_id_and_does_not_credit_a_fix(self):   # AE3
        blocks = self.cap["rebuild_v"]["blocks"]
        cl1, cl2 = self.cl, checklist(EDITED)

        def rec(cl, run_id):
            res = review(cl, blocks)
            r = FindingsRecord(run_id=run_id, baseline={"slug": "b", "hash": "h", "path": "b.md"},
                               page={"key": "p", "kind": "file", "snapshot": "s", "styles_vendored": True},
                               findings=res.findings, items=cl.items)
            assign_numbers(r)
            return r

        round1, round2 = rec(cl1, "1"), rec(cl2, "2")
        diff = diff_records(round1, round2)
        replaced = [e for e in diff.entries if e.category == "replaces"]
        self.assertEqual(len(replaced), 1)
        self.assertEqual(len(diff.pairs), 1)
        self.assertIn("nearly two decades", diff.pairs[0].old_text)
        self.assertIn("over two decades", diff.pairs[0].new_text)
        self.assertFalse([e for e in diff.entries if e.category == "fixed"])
        report = render_report(round2, diff)
        self.assertIn("†", report)
        self.assertNotIn("†", render_agency_block(round2))


if __name__ == "__main__":
    unittest.main()
