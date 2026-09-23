import pathlib
import tempfile
import unittest

from qa_review.intake import (
    Checklist, IntakeError, build_checklist, confirm, is_confirmed, load_frozen, read_markdown,
    write_checklist,
)
from qa_review.checklist_view import render_view
from qa_review.schema import ChecklistItem
from tests.support import BASELINE, MINI, intake_stub, to_docx, write_tmp


class IntakeTests(unittest.TestCase):
    def test_committed_baseline_counts(self):
        cl = build_checklist(BASELINE, intake_stub(structural_index=4, consistency_marker="Blackwing Comparison"))
        self.assertEqual(cl.counts_by_type()["verbatim"], 15 + 7 * 3)  # 15 boxed quotes + 21 body cells
        self.assertEqual(sum(1 for i in cl.items if i.type == "structural"), 1)
        self.assertEqual(sum(1 for i in cl.items if i.type == "judgment" and not i.refs), 4)
        self.assertEqual(sum(1 for i in cl.items if i.refs), 1)   # the consistency item
        self.assertTrue(cl.guard["applicable"])
        self.assertTrue(all(i.id for i in cl.items))

    def test_header_row_is_not_a_separate_item(self):
        cl = build_checklist(BASELINE, intake_stub())
        self.assertNotIn("Spec label", [i.text for i in cl.items])
        self.assertTrue(any("2026 CT5-V" in i.text and "VS" in i.text for i in cl.items))

    def test_docx_matches_markdown_ids_and_texts(self):
        stub = lambda: intake_stub(structural_index=4)
        a = build_checklist(BASELINE, stub())
        with tempfile.TemporaryDirectory() as d:
            b = build_checklist(to_docx(BASELINE, pathlib.Path(d) / "b.docx"), stub())
        self.assertEqual([(i.id, i.type) for i in a.items], [(i.id, i.type) for i in b.items])

    def test_count_guard_stops_when_parser_drops_a_quote(self):
        p = write_tmp(MINI)
        import qa_review.intake as intake
        real = intake.extract_items
        def dropping(elements):
            items, conds = real(elements)
            return items[:-1], conds
        intake.extract_items = dropping
        try:
            with self.assertRaises(IntakeError) as cm:
                build_checklist(p, intake_stub())
            self.assertIn("count guard", str(cm.exception))
        finally:
            intake.extract_items = real

    def test_model_dropping_a_condition_fails_intake(self):
        from qa_review.model import StubModel
        p = write_tmp(MINI)
        bad = StubModel({"intake": {"conditions": [{"index": 0, "type": "judgment", "subjects": []}],
                                    "consistency": []}})
        with self.assertRaises(IntakeError):
            build_checklist(p, bad)

    def test_model_naming_a_missing_subject_fails_intake(self):
        from qa_review.model import StubModel
        p = write_tmp(MINI)
        bad = StubModel({"intake": {"conditions": [
            {"index": 0, "type": "judgment", "subjects": ["nope.000000"]},
            {"index": 1, "type": "structural", "subjects": []}], "consistency": []}})
        with self.assertRaises(IntakeError):
            build_checklist(p, bad)

    def test_structural_condition_with_no_subjects_fails_intake_not_review(self):
        from qa_review.model import StubModel
        p = write_tmp(MINI)
        bad = StubModel({"intake": {
            "conditions": [{"index": 0, "type": "judgment", "subjects": []},
                           {"index": 1, "type": "structural", "subjects": []}],
            "consistency": []}})
        with self.assertRaises(IntakeError) as cm:
            build_checklist(p, bad)
        self.assertIn("no subject", str(cm.exception))

    def test_identical_labels_get_distinct_ids_and_edit_changes_only_that_id(self):
        a = build_checklist(write_tmp(MINI), intake_stub())
        buy = [i for i in a.items if i.text == "Buy now"]
        self.assertEqual(len(buy), 2)
        self.assertNotEqual(buy[0].id, buy[1].id)
        b = build_checklist(write_tmp(MINI.replace("$10", "$11")), intake_stub())
        changed = {x.id for x in a.items} ^ {x.id for x in b.items}
        self.assertEqual(len(changed), 2)   # one id retired, one added

    def test_identical_condition_wording_gets_distinct_ids(self):
        # testing:test_runner.py:45 -- without an ordinal, two conditions repeating the same
        # wording in one section collided on one ID and run_review rejected the whole checklist.
        text = MINI.replace(
            "1. The note is present whenever any price appears.\n2. The note is visible on page load.",
            "1. The note is present whenever any price appears.\n"
            "2. The note is present whenever any price appears.")
        cl = build_checklist(write_tmp(text), intake_stub())
        dup = [i for i in cl.items if i.text == "The note is present whenever any price appears."]
        self.assertEqual(len(dup), 2)
        self.assertNotEqual(dup[0].id, dup[1].id)

    def test_no_countable_structure_fails_intake_cleanly(self):
        # An empty checklist that "passes" review by having nothing to fail is the same
        # false-confidence defect the coverage contract exists to prevent (correctness:runner.py:36).
        p = write_tmp("# Doc\n\n## Section\n\nJust prose here.\n")
        with self.assertRaises(IntakeError) as cm:
            build_checklist(p, intake_stub())
        self.assertIn("nothing to review", str(cm.exception))

    def test_consistency_item_id_is_stable_when_model_rewords_label(self):
        base = MINI
        a = build_checklist(write_tmp(base), intake_stub(consistency_marker="Widget Deluxe"))
        stub = intake_stub(consistency_marker="Widget Deluxe")
        orig = stub.answers["intake"]
        def reworded(prompt):
            out = orig(prompt)
            for c in out["consistency"]:
                c["text"] = "Different wording of the same check."
            return out
        stub.answers["intake"] = reworded
        b = build_checklist(write_tmp(base), stub)
        ida = [i.id for i in a.items if i.refs]
        idb = [i.id for i in b.items if i.refs]
        self.assertEqual(ida, idb)
        self.assertEqual(len(ida), 1)

    def test_consistency_item_references_the_year_bearing_items(self):
        cl = build_checklist(BASELINE, intake_stub(consistency_marker="Blackwing Comparison"))
        cons = [i for i in cl.items if i.refs][0]
        texts = {i.id: i.text for i in cl.items}
        self.assertTrue(all("Blackwing Comparison" in texts[r] for r in cons.refs))
        self.assertGreaterEqual(len(cons.refs), 3)

    def test_view_lists_every_item_with_counts_header(self):
        cl = build_checklist(BASELINE, intake_stub(structural_index=4))
        view = render_view(cl)
        self.assertIn("verbatim", view.splitlines()[2])
        for i in cl.items:
            self.assertIn(i.id, view)

    def test_frozen_checklist_and_confirmation_track_baseline_hash(self):
        p = write_tmp(MINI)
        cl = build_checklist(p, intake_stub())
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            write_checklist(d, cl)
            self.assertFalse(is_confirmed(d, cl))
            confirm(d)
            self.assertTrue(is_confirmed(d, cl))
            self.assertEqual(load_frozen(d).baseline_hash, cl.baseline_hash)
            # a changed baseline has a different hash, so the old confirmation does not apply
            other = build_checklist(write_tmp(MINI.replace("Buy now", "Buy today")), intake_stub())
            self.assertFalse(is_confirmed(d, other))

    def test_confirmation_does_not_survive_a_content_change_at_the_same_baseline_hash(self):
        # adversarial:cli.py:58 -- reverting an edited baseline back to its confirmed content
        # re-runs intake (checklist.json was overwritten by the edit), and a fresh model call
        # can type a condition's subjects, type or a consistency check differently the second
        # time -- same baseline hash, different checklist. The old baseline-hash-only stamp
        # would still read "confirmed" for a checklist the PMM never actually saw.
        p = write_tmp(MINI)
        seen = build_checklist(p, intake_stub())
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            write_checklist(d, seen)
            confirm(d)
            self.assertTrue(is_confirmed(d, seen))

            drifted_items = list(seen.items)
            last = drifted_items[-1].to_dict()
            last["text"] = last["text"] + " (typed differently on rerun)"
            drifted_items[-1] = ChecklistItem(**last)
            drifted = Checklist(drifted_items, seen.baseline, seen.guard)
            self.assertEqual(drifted.baseline_hash, seen.baseline_hash)   # same baseline, same hash
            write_checklist(d, drifted)     # as cmd_intake would after re-running the model
            self.assertFalse(is_confirmed(d, drifted))


class MarkdownGrammarTests(unittest.TestCase):
    """adversarial:intake.py:117 -- unrecognized structure used to vanish silently (dropped by
    the extractor, and re-agreed-with by the count guard's raw pass using the same grammar).
    A checklist missing an item still reports full coverage; these must fail loud instead."""

    def test_wrapped_condition_lines_are_folded_into_the_open_condition(self):
        text = ("1. The disclaimer lists all six exclusions in this order: freight,\n"
               "tax, title, license, dealer fees, optional equipment.\n\n"
               "> a real quote")
        els = read_markdown(text)
        condition = [e for e in els if e.kind == "condition"][0]
        self.assertEqual(condition.text,
                         "The disclaimer lists all six exclusions in this order: freight, "
                         "tax, title, license, dealer fees, optional equipment.")

    def test_a_blank_line_ends_the_open_condition_so_later_prose_is_not_folded_in(self):
        text = "1. First condition.\n\nSome unrelated prose paragraph elsewhere in the doc."
        els = read_markdown(text)
        condition = [e for e in els if e.kind == "condition"][0]
        self.assertEqual(condition.text, "First condition.")

    def test_indented_quote_fails_intake_naming_the_line(self):
        text = "> a normal quote\n\n  > an indented quote that would otherwise vanish"
        with self.assertRaises(IntakeError) as cm:
            read_markdown(text)
        self.assertIn("line 3", str(cm.exception))

    def test_paren_numbered_condition_fails_intake_naming_the_line(self):
        text = "1. First condition.\n2) paren-numbered condition"
        with self.assertRaises(IntakeError) as cm:
            read_markdown(text)
        self.assertIn("line 2", str(cm.exception))

    def test_indented_numbered_condition_fails_intake(self):
        text = "1. First condition.\n  2. indented condition"
        with self.assertRaises(IntakeError):
            read_markdown(text)

    def test_bulleted_list_fails_intake_naming_the_line(self):
        text = "1. First condition.\n\n- a bullet that would otherwise be silently ignored"
        with self.assertRaises(IntakeError) as cm:
            read_markdown(text)
        self.assertIn("line 3", str(cm.exception))

    def test_code_fence_fails_intake(self):
        text = "1. First condition.\n\n```\nsome fenced block\n```"
        with self.assertRaises(IntakeError):
            read_markdown(text)

    def test_well_formed_documents_are_unaffected(self):
        # the exact grammar this all has to keep working for
        read_markdown(MINI)
        read_markdown(pathlib.Path(BASELINE).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
