import unittest

from qa_review.checks import check_structural, check_verbatim
from qa_review.schema import ChecklistItem, PageBlock


def blk(i, text, table=None, visible="visible", kind="block"):
    return PageBlock(index=i, kind=kind, text=text, path=f"p{i}", visible=visible, table=table)


def verbatim(text, loc=None, id_="s.aaaaaa"):
    return ChecklistItem(id=id_, section="s", type="verbatim", text=text, locator=loc)


class VerbatimTests(unittest.TestCase):
    def test_exact_block_passes(self):
        r = check_verbatim(verbatim("Hello world."), [blk(0, "Other"), blk(1, "Hello world.")], 0)
        self.assertEqual((r.verdict, r.block), ("PASS", 1))

    def test_one_word_change_fails_with_page_text_and_diff(self):
        approved = "Born and bred, nearly two decades of engineering"
        r = check_verbatim(verbatim(approved), [blk(0, "Born and bred, over two decades of engineering")], 0)
        self.assertEqual(r.verdict, "FAIL")
        self.assertEqual(r.quote, "Born and bred, over two decades of engineering")
        self.assertIn("nearly", r.explanation)
        self.assertIn("over", r.explanation)

    def test_absent_is_not_found(self):
        r = check_verbatim(verbatim("A completely different sentence about nothing"), [blk(0, "Zzz qqq")], 0)
        self.assertEqual(r.verdict, "NOT FOUND ON PAGE")

    def test_identical_items_map_to_identical_blocks_by_order(self):
        blocks = [blk(0, "Buy now"), blk(1, "x"), blk(2, "Buy now")]
        a = check_verbatim(verbatim("Buy now"), blocks, 0)
        b = check_verbatim(verbatim("Buy now", id_="s.aaaaaa-2"), blocks, 1)
        self.assertEqual((a.block, b.block), (0, 2))
        c = check_verbatim(verbatim("Buy now", id_="s.aaaaaa-3"), blocks, 2)
        self.assertEqual(c.verdict, "NOT FOUND ON PAGE")

    def test_typography_difference_passes(self):
        r = check_verbatim(verbatim("You'll learn"), [blk(0, "You’ll learn")], 0)
        self.assertEqual(r.verdict, "PASS")

    def test_whole_token_span_inside_longer_block_passes(self):
        r = check_verbatim(verbatim("Home » 2026 Widget"),
                           [blk(0, "You are here: Home » 2026 Widget")], 0)
        self.assertEqual(r.verdict, "PASS")

    def test_partial_word_span_does_not_pass(self):
        r = check_verbatim(verbatim("Buy now"), [blk(0, "Buy nowhere")], 0)
        self.assertNotEqual(r.verdict, "PASS")

    def test_table_cell_matches_by_coordinate(self):
        loc = {"table": 0, "row": 0, "col": 0}
        blocks = [blk(0, "$58,900", table=loc), blk(1, "$57,600", table={"table": 0, "row": 3, "col": 0})]
        r = check_verbatim(verbatim("$57,600", loc), blocks, 0)
        self.assertEqual((r.verdict, r.quote), ("FAIL", "$58,900"))

    def test_label_missing_asterisk_fails(self):
        loc = {"table": 0, "row": 0, "col": 1}
        r = check_verbatim(verbatim("Starting MSRP*", loc), [blk(0, "Starting MSRP", table=loc)], 0)
        self.assertEqual(r.verdict, "FAIL")

    def test_header_quote_with_dividers_matches_one_table_row(self):
        blocks = [blk(0, "Left", table={"table": 0, "row": -1, "col": 0}),
                  blk(1, "VS", table={"table": 0, "row": -1, "col": 1}),
                  blk(2, "Right", table={"table": 0, "row": -1, "col": 2})]
        q = "Left   |   VS   |   Right"
        self.assertEqual(check_verbatim(verbatim(q), blocks, 0).verdict, "PASS")
        blocks[2] = blk(2, "Righ", table={"table": 0, "row": -1, "col": 2})
        self.assertEqual(check_verbatim(verbatim(q), blocks, 0).verdict, "FAIL")

    def test_title_block_matches_a_quote_containing_a_divider(self):
        title = blk(0, "2026 X vs. 2025 X | Dealer", kind="title")
        r = check_verbatim(verbatim("2026 X vs. 2025 X | Dealer"), [title], 0)
        self.assertEqual(r.verdict, "PASS")

    def test_missing_table_locator_is_not_found_not_a_page_wide_guess(self):
        # AE-VERBATIM-1: a deleted row/column means no cell at the approved location. Falling
        # through to a whole-page token search let an unrelated block (a different table, a
        # hidden block, the title) silently PASS a defect that removed the row entirely.
        loc = {"table": 0, "row": 5, "col": 1}
        blocks = [blk(0, "Trunk space of 13.7 cu ft fits luggage")]   # the true row is gone
        r = check_verbatim(verbatim("13.7 cu ft", loc), blocks, 0)
        self.assertEqual(r.verdict, "NOT FOUND ON PAGE")

    def test_locator_mismatch_at_a_shifted_table_index_warns_not_fails(self):
        # correctness:73 -- the page's table index counts every <table> in the DOM, the
        # baseline's counts only approved-doc tables; an unrelated table earlier on the page
        # shifts every index after it, so the same row/col can legitimately live at a
        # different table number without the value having actually changed.
        loc = {"table": 0, "row": 2, "col": 0}
        blocks = [blk(0, "$58,900", table=loc),
                  blk(1, "$57,600", table={"table": 1, "row": 2, "col": 0})]
        r = check_verbatim(verbatim("$57,600", loc), blocks, 0)
        self.assertEqual(r.verdict, "WARN")
        self.assertTrue(r.check_by_eye)
        self.assertEqual(r.quote, "$57,600")

    def test_locator_mismatch_with_no_shifted_match_still_fails(self):
        # A genuine value change at a different row must not be swept into the shifted-index
        # allowance above: same test data as test_table_cell_matches_by_coordinate.
        loc = {"table": 0, "row": 0, "col": 0}
        blocks = [blk(0, "$58,900", table=loc), blk(1, "$57,600", table={"table": 0, "row": 3, "col": 0})]
        r = check_verbatim(verbatim("$57,600", loc), blocks, 0)
        self.assertEqual((r.verdict, r.quote), ("FAIL", "$58,900"))

    def test_span_match_inside_the_title_warns_instead_of_passing(self):
        # adversarial:81 -- the H1 was altered but the tab title still contains the old text;
        # a naive token-span match silently cites the title and PASSes the altered H1 item.
        title = blk(0, "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison | Crestmont", kind="title")
        h1 = blk(1, "2026 CT5-V vs 2026 CT5-V Blackwing Comparison")   # altered: no period after "vs"
        r = check_verbatim(verbatim("2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"), [h1, title], 0)
        self.assertEqual(r.verdict, "WARN")
        self.assertTrue(r.check_by_eye)
        self.assertIn("title", r.explanation)

    def test_span_match_inside_a_hidden_block_warns_instead_of_passing(self):
        blocks = [blk(0, "This copy is hidden: Dealer sets final price.", visible="hidden")]
        r = check_verbatim(verbatim("Dealer sets final price."), blocks, 0)
        self.assertEqual(r.verdict, "WARN")
        self.assertTrue(r.check_by_eye)
        self.assertIn("hidden", r.explanation)

    def test_a_hidden_decoy_duplicate_does_not_get_cited_over_the_visible_copy(self):
        # correctness:83 -- a hidden print-only/aria-hidden duplicate must not be the block a
        # structural (visible-on-load) condition ends up checking instead of the real, visible one.
        blocks = [blk(0, "Dealer sets final price.", visible="hidden"),
                  blk(1, "Dealer sets final price.", visible="visible")]
        r = check_verbatim(verbatim("Dealer sets final price."), blocks, 0)
        self.assertEqual((r.verdict, r.block), ("PASS", 1))

    def test_glued_asterisk_dagger_and_decimal_do_not_pass(self):
        # adversarial:47 -- a whole-token-span check that only rejects an alphanumeric
        # neighbour lets an added footnote mark or a decimal continuation through.
        cases = [("$57,600", "$57,600.99"), ("Starting MSRP", "Starting MSRP*"),
                 ("10", "10.5"), ("Heads-Up Display", "Heads-Up Display†")]
        for approved, page in cases:
            with self.subTest(approved=approved, page=page):
                r = check_verbatim(verbatim(approved), [blk(0, page)], 0)
                self.assertNotEqual(r.verdict, "PASS")


class StructuralTests(unittest.TestCase):
    def setUp(self):
        self.item = ChecklistItem(id="c.1", section="s", type="structural", text="visible on load",
                                  subjects=["disc.1"])
        self.blocks = [blk(0, "Disclaimer text")]
        from qa_review.schema import Finding
        self.Finding = Finding

    def result(self, visible):
        self.blocks[0].visible = visible
        prior = {"disc.1": self.Finding(item_id="disc.1", verdict="PASS", block=0)}
        return check_structural(self.item, prior, self.blocks)

    def test_visible_passes_hidden_fails_undetermined_warns_for_a_look(self):
        self.assertEqual(self.result("visible").verdict, "PASS")
        self.assertEqual(self.result("hidden").verdict, "FAIL")
        r = self.result("undetermined")
        self.assertEqual(r.verdict, "WARN")
        self.assertTrue(r.check_by_eye)

    def test_subject_not_found_is_not_found(self):
        prior = {"disc.1": self.Finding(item_id="disc.1", verdict="NOT FOUND ON PAGE", block=None)}
        self.assertEqual(check_structural(self.item, prior, self.blocks).verdict, "NOT FOUND ON PAGE")


if __name__ == "__main__":
    unittest.main()


class StructuralEvidenceTests(unittest.TestCase):
    def test_visibility_is_part_of_a_structural_verdict_evidence(self):
        from qa_review.schema import Finding
        item = ChecklistItem(id="c.1", section="s", type="structural", text="v", subjects=["d.1"])
        prior = {"d.1": Finding(item_id="d.1", verdict="PASS", block=0)}
        hidden = check_structural(item, prior, [blk(0, "Same text", visible="hidden")])
        shown = check_structural(item, prior, [blk(0, "Same text", visible="visible")])
        self.assertNotEqual(hidden.evidence_hash, shown.evidence_hash)
