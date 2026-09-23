import unittest

from qa_review.diff import diff_records
from qa_review.schema import ChecklistItem, Finding, FindingsRecord


def item(id_, text, section="s", type_="verbatim"):
    return ChecklistItem(id=id_, section=section, type=type_, text=text)


def find(id_, verdict, evidence="e1", text=""):
    return Finding(item_id=id_, verdict=verdict, approved_text=text, evidence_hash=evidence,
                   cited=[evidence] if evidence else [])


def record(items, findings):
    return FindingsRecord(run_id="r", baseline={"slug": "b", "hash": "h", "path": "b.md"},
                          page={"key": "p", "kind": "file", "snapshot": "s", "styles_vendored": True},
                          findings=findings, items=items)


def cats(d):
    return {e.item_id: e.category for e in d.entries}


class DiffTests(unittest.TestCase):
    def test_no_prior_means_no_diff(self):
        self.assertIsNone(diff_records(None, record([item("a", "x")], [find("a", "PASS")])))

    def test_identical_inputs_report_nothing_changed(self):
        r = record([item("a", "x"), item("b", "y")], [find("a", "PASS"), find("b", "FAIL")])
        d = diff_records(r, r)
        self.assertEqual({e.category for e in d.entries}, {"still open"})
        self.assertEqual(d.unchanged, 1)
        self.assertFalse([e for e in d.entries if e.category in ("fixed", "regressed", "new")])

    def test_fail_to_pass_with_changed_evidence_is_fixed_and_the_reverse_is_regressed(self):
        items = [item("a", "x"), item("b", "y")]
        prior = record(items, [find("a", "FAIL", "old page text"), find("b", "PASS", "same")])
        cur = record(items, [find("a", "PASS", "new page text"), find("b", "FAIL", "changed")])
        self.assertEqual(cats(diff_records(prior, cur)), {"a": "fixed", "b": "regressed"})

    def test_a_verdict_flip_over_identical_evidence_is_flagged_not_fixed(self):
        items = [item("a", "x")]
        prior = record(items, [find("a", "FAIL", "same")])
        cur = record(items, [find("a", "PASS", "same")])
        self.assertEqual(cats(diff_records(prior, cur)), {"a": "verdict changed, page unchanged"})

    def test_not_found_that_is_now_found_is_fixed(self):
        items = [item("a", "x")]
        prior = record(items, [find("a", "NOT FOUND ON PAGE", "")])
        cur = record(items, [find("a", "PASS", "found it")])
        self.assertEqual(cats(diff_records(prior, cur)), {"a": "fixed"})

    def test_a_new_failing_item_is_new_and_a_new_passing_item_is_not_listed(self):
        prior = record([item("a", "x")], [find("a", "PASS")])
        cur = record([item("a", "x"), item("n", "z"), item("m", "w")],
                     [find("a", "PASS"), find("n", "FAIL", "e"), find("m", "PASS", "e")])
        self.assertEqual(cats(diff_records(prior, cur)), {"n": "new"})

    def test_an_edited_approved_line_is_replaced_not_fixed(self):                       # AE3
        old_text = "Born and bred, nearly two decades of relentless engineering."
        new_text = "Born and bred, over two decades of relentless engineering."
        prior = record([item("s.old", old_text)], [find("s.old", "FAIL", "over two decades", old_text)])
        cur = record([item("s.new", new_text)], [find("s.new", "PASS", "over two decades", new_text)])
        d = diff_records(prior, cur)
        self.assertEqual(cats(d), {"s.new": "replaces"})
        self.assertEqual(d.entries[0].replaces, "s.old")
        self.assertEqual(d.pairs[0].old_text, old_text)
        self.assertEqual(d.pairs[0].new_text, new_text)
        self.assertEqual(d.removed, [])

    def test_a_replaced_id_is_listed_whatever_its_verdict(self):
        prior = record([item("s.old", "Born and bred, nearly two decades of engineering.")],
                       [find("s.old", "PASS", "x")])
        cur = record([item("s.new", "Born and bred, over two decades of engineering.")],
                     [find("s.new", "FAIL", "y")])
        self.assertEqual(cats(diff_records(prior, cur)), {"s.new": "replaces"})

    def test_a_deleted_baseline_line_is_listed_as_removed(self):
        prior = record([item("a", "x"), item("gone", "some old approved line here")],
                       [find("a", "PASS"), find("gone", "FAIL", "e", "some old approved line here")])
        cur = record([item("a", "x")], [find("a", "PASS")])
        d = diff_records(prior, cur)
        self.assertEqual([r.item_id for r in d.removed], ["gone"])
        self.assertNotIn("gone", cats(d))

    def test_a_changed_set_of_model_proposed_consistency_checks_is_not_a_baseline_edit(self):
        cons_old = ChecklistItem(id="consistency.old", section="consistency", type="judgment",
                                 text="Names must agree everywhere.", refs=["a", "b"], label="names")
        prior = record([item("a", "x"), cons_old], [find("a", "PASS"), find("consistency.old", "FAIL", "e")])
        cons_new = ChecklistItem(id="consistency.new", section="consistency", type="judgment",
                                 text="Names must agree everywhere.", refs=["a", "b"], label="names v2")
        cur = record([item("a", "x"), cons_new], [find("a", "PASS"), find("consistency.new", "PASS", "e")])
        d = diff_records(prior, cur)
        self.assertEqual(d.removed, [])
        self.assertEqual(d.pairs, [])
        self.assertNotIn("consistency.old", cats(d))


if __name__ == "__main__":
    unittest.main()
