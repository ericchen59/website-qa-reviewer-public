import unittest

from qa_review import checks
from qa_review.model import StubModel
from qa_review.runner import CoverageError, run_review
from qa_review.schema import ChecklistItem, PageBlock


def blk(i, text, table=None, visible="visible", kind="block"):
    return PageBlock(index=i, kind=kind, text=text, path=f"p{i}", visible=visible, table=table)


def items():
    return [
        ChecklistItem(id="a.1", section="a", type="verbatim", text="Buy now"),
        ChecklistItem(id="a.2", section="a", type="verbatim", text="Price excludes tax"),
        ChecklistItem(id="l.1", section="l", type="structural", text="visible on load", subjects=["a.2"]),
        ChecklistItem(id="l.2", section="l", type="judgment", text="a note is present", subjects=["a.2"]),
    ]


PAGE = [blk(0, "T", kind="title"), blk(1, "Buy now"), blk(2, "Price excludes tax")]
STUB = lambda: StubModel({"l.2": {"verdict": "PASS", "quote": "Price excludes tax", "reason": "ok"}})


class RunnerTests(unittest.TestCase):
    def test_one_verdict_per_item_in_checklist_order(self):
        res = run_review(items(), PAGE, STUB())
        self.assertEqual([f.item_id for f in res.findings], ["a.1", "a.2", "l.1", "l.2"])
        self.assertTrue(all(f.verdict == "PASS" for f in res.findings))

    def test_empty_checklist_raises_instead_of_a_vacuous_clean_pass(self):
        # correctness:runner.py:36 -- an empty checklist trivially "satisfies" the coverage
        # contract (nothing missing, nothing duplicated) and used to produce a clean report.
        with self.assertRaises(CoverageError) as cm:
            run_review([], PAGE, STUB())
        self.assertIn("no items", str(cm.exception))

    def test_missing_verdict_raises_naming_the_item_and_returns_nothing(self):       # AE1
        real = checks.check_verbatim
        checks.check_verbatim = lambda item, blocks, occ: None if item.id == "a.2" else real(item, blocks, occ)
        try:
            with self.assertRaises(CoverageError) as cm:
                run_review(items(), PAGE, STUB())
            self.assertIn("a.2", str(cm.exception))
        finally:
            checks.check_verbatim = real

    def test_duplicate_verdict_raises(self):
        # testing:test_runner.py:45 -- a real duplicate-ID checklist (two items sharing one
        # id), rather than patching runner's test-only _collect identity hook, which proved
        # only that the message exists, not that a real checklist can trigger it.
        dup = items() + [ChecklistItem(id="a.1", section="a", type="verbatim", text="Buy now")]
        with self.assertRaises(CoverageError) as cm:
            run_review(dup, PAGE, STUB())
        self.assertIn("a.1", str(cm.exception))

    def test_typography_rules_applied_are_reported(self):
        page = [blk(0, "T", kind="title"), blk(1, "Buy now"), blk(2, "Price excludes tax")]
        res = run_review(items(), page, STUB())
        self.assertIn("non-breaking space to space", res.typography_rules)

    def test_hidden_subject_fails_the_structural_item_only(self):
        page = [blk(0, "T", kind="title"), blk(1, "Buy now"), blk(2, "Price excludes tax", visible="hidden")]
        res = {f.item_id: f for f in run_review(items(), page, STUB()).findings}
        self.assertEqual(res["l.1"].verdict, "FAIL")
        self.assertEqual(res["a.2"].verdict, "PASS")


if __name__ == "__main__":
    unittest.main()
