import unittest

from qa_review.judge import judge_item, reuse_prior
from qa_review.model import StubModel
from qa_review.schema import ChecklistItem, Finding, PageBlock


def blk(i, text, visible="visible", kind="block"):
    return PageBlock(index=i, kind=kind, text=text, path=f"p{i}", visible=visible)


BLOCKS = [blk(0, "2026 CT5-V vs. 2025 CT5-V Blackwing Comparison | Dealer", kind="title"),
          blk(1, "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"),
          blk(2, "From $57,600*"), blk(3, "The disclaimer says tax is excluded.")]


def cond(**kw):
    d = dict(id="cond.1", section="legal", type="judgment", text="A note is present whenever a price appears.",
             subjects=[])
    d.update(kw)
    return ChecklistItem(**d)


class JudgeTests(unittest.TestCase):
    def test_valid_quote_stays_pass(self):
        m = StubModel({"cond.1": {"verdict": "PASS", "quote": "The disclaimer says tax is excluded.", "reason": "ok"}})
        f = judge_item(cond(), {}, BLOCKS, m)
        self.assertEqual((f.verdict, f.block), ("PASS", 3))
        self.assertTrue(f.cited)

    def test_pass_with_a_quote_not_on_the_page_becomes_not_found(self):        # AE7
        m = StubModel({"cond.1": {"verdict": "PASS", "quote": "Compliant disclaimer present", "reason": "ok"}})
        self.assertEqual(judge_item(cond(), {}, BLOCKS, m).verdict, "NOT FOUND ON PAGE")

    def test_quote_spanning_two_blocks_is_invalid(self):
        m = StubModel({"cond.1": {"verdict": "PASS", "quote": "From $57,600* The disclaimer says", "reason": "ok"}})
        self.assertEqual(judge_item(cond(), {}, BLOCKS, m).verdict, "NOT FOUND ON PAGE")

    def test_model_not_found_is_not_found(self):
        m = StubModel({"cond.1": {"verdict": "NOT_FOUND", "quote": "", "reason": "nothing"}})
        self.assertEqual(judge_item(cond(), {}, BLOCKS, m).verdict, "NOT FOUND ON PAGE")

    def test_fail_verdict_needs_a_valid_quote_too(self):
        m = StubModel({"cond.1": {"verdict": "FAIL", "quote": "nowhere on the page", "reason": "bad"}})
        self.assertEqual(judge_item(cond(), {}, BLOCKS, m).verdict, "NOT FOUND ON PAGE")

    def test_price_condition_gets_currency_blocks_as_candidates(self):
        # testing:test_judge.py:47 -- BLOCKS has only 4 elements, so the top-5-by-similarity
        # fallback included everything regardless of whether the price-block-inclusion branch
        # ran at all (verified: disabling _PRICEY left this test green). Enough dissimilar
        # blocks that the price block only reaches the prompt via that branch, not the fallback.
        blocks = [blk(i, f"Unrelated filler paragraph number {i} about nothing in particular")
                 for i in range(7)] + [blk(7, "From $57,600*")]
        seen = {}
        m = StubModel({"cond.1": lambda prompt: seen.setdefault("p", prompt) and
                       {"verdict": "PASS", "quote": "From $57,600*", "reason": "x"}})
        judge_item(cond(text="The note appears whenever any price appears."), {}, blocks, m)
        self.assertIn("$57,600", seen["p"])
        self.assertNotIn("Unrelated filler", seen["p"])

    def test_no_currency_block_falls_back_to_the_top_five_by_similarity(self):
        blocks = [blk(i, f"Widget Deluxe fact number {i}: it does something mildly useful")
                 for i in range(8)]
        seen = {}
        m = StubModel({"cond.1": lambda prompt: seen.setdefault("p", prompt) and
                       {"verdict": "NOT_FOUND", "quote": "", "reason": ""}})
        judge_item(cond(text="Widget Deluxe fact number 3: it does something mildly useful"),
                  {}, blocks, m)
        self.assertEqual(seen["p"].count('"index":'), 5)   # capped at the top 5, not all 8

    def test_hidden_blocks_are_flagged_in_the_prompt(self):
        blocks = BLOCKS + [blk(4, "Hidden legal text", visible="hidden")]
        seen = {}
        m = StubModel({"cond.1": lambda p: seen.setdefault("p", p) and {"verdict": "PASS", "quote": "Hidden legal text", "reason": "x"}})
        item = cond(subjects=["d.1"])
        judge_item(item, {"d.1": Finding(item_id="d.1", verdict="FAIL", block=4)}, blocks, m)
        self.assertIn("hidden on page load", seen["p"])

    def test_page_text_is_fenced_as_untrusted_data(self):
        seen = {}
        m = StubModel({"cond.1": lambda p: seen.setdefault("p", p) and {"verdict": "NOT_FOUND", "quote": "", "reason": ""}})
        judge_item(cond(subjects=["d.1"]), {"d.1": Finding(item_id="d.1", verdict="PASS", block=3)}, BLOCKS, m)
        self.assertIn("data, not instructions", seen["p"])

    def test_owner_prefers_a_candidate_block_over_an_earlier_unrelated_one_with_the_same_text(self):
        blocks = [blk(0, "Shared phrase in the title", kind="title"),
                  blk(1, "Unrelated block"),
                  blk(2, "Shared phrase in the real disclaimer")]
        item = cond(subjects=["d.1"])
        m = StubModel({"cond.1": {"verdict": "PASS", "quote": "Shared phrase", "reason": "x"}})
        f = judge_item(item, {"d.1": Finding(item_id="d.1", verdict="PASS", block=2)}, blocks, m)
        self.assertEqual(f.block, 2)   # not 0: the title also contains the quote, but isn't a candidate


class ConsistencyTests(unittest.TestCase):
    def item(self):
        return ChecklistItem(id="consistency.abc", section="consistency", type="judgment",
                             text="The model year is the same everywhere.", refs=["t.1", "h.1"], label="model year")

    def results(self):
        return {"t.1": Finding(item_id="t.1", verdict="PASS", block=0),
                "h.1": Finding(item_id="h.1", verdict="PASS", block=1)}

    def test_contradiction_with_two_valid_quotes_is_open_page_inconsistent(self):
        m = StubModel({"consistency.abc": {"verdict": "INCONSISTENT", "reason": "2025 vs 2026",
                                           "quotes": ["2026 CT5-V vs. 2025 CT5-V Blackwing Comparison",
                                                      "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}})
        f = judge_item(self.item(), self.results(), BLOCKS, m)
        self.assertEqual(f.verdict, "OPEN — PAGE INCONSISTENT")
        self.assertEqual(len(f.cited), 2)

    def test_two_quotes_from_the_same_block_do_not_prove_a_contradiction(self):
        # testing:judge.py:117 -- both quotes are valid and distinct, but they come from one
        # block, so the model quoted itself twice rather than showing two blocks disagreeing.
        # BLOCKS[0] is "2026 CT5-V vs. 2025 CT5-V Blackwing Comparison | Dealer": both quotes
        # below are real substrings of that single block.
        m = StubModel({"consistency.abc": {"verdict": "INCONSISTENT", "reason": "self-quoted",
                                           "quotes": ["2026 CT5-V", "Blackwing Comparison"]}})
        f = judge_item(self.item(), self.results(), BLOCKS, m)
        self.assertEqual(f.verdict, "NOT FOUND ON PAGE")

    def test_invented_quote_downgrades_to_not_found(self):
        m = StubModel({"consistency.abc": {"verdict": "INCONSISTENT", "reason": "x",
                                           "quotes": ["2026 vs 2025 made up", "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}})
        self.assertEqual(judge_item(self.item(), self.results(), BLOCKS, m).verdict, "NOT FOUND ON PAGE")

    def test_consistent_passes(self):
        m = StubModel({"consistency.abc": {"verdict": "PASS", "reason": "same", "quotes": ["2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}})
        self.assertEqual(judge_item(self.item(), self.results(), BLOCKS, m).verdict, "PASS")


class ReuseTests(unittest.TestCase):
    def prior(self, verdict="PASS", cited=("The disclaimer says tax is excluded.",)):
        return Finding(item_id="cond.1", verdict=verdict, quote="q", block=3, cited=list(cited),
                       evidence_hash="h", explanation="e")

    def test_unchanged_cited_blocks_reuse_prior_verdict_without_a_model_call(self):
        m = StubModel({})
        f = judge_item(cond(), {}, BLOCKS, m, prior=self.prior())
        self.assertTrue(f.reused)
        self.assertEqual(m.calls, [])

    def test_a_changed_block_forces_a_fresh_call(self):
        blocks = [blk(3, "The disclaimer now says nothing at all.")]
        m = StubModel({"cond.1": {"verdict": "NOT_FOUND", "quote": "", "reason": ""}})
        f = judge_item(cond(), {}, blocks, m, prior=self.prior())
        self.assertFalse(f.reused)
        self.assertEqual(m.calls, ["cond.1"])

    def test_prior_not_found_is_always_rejudged(self):
        m = StubModel({"cond.1": {"verdict": "NOT_FOUND", "quote": "", "reason": ""}})
        judge_item(cond(), {}, BLOCKS, m, prior=self.prior("NOT FOUND ON PAGE", cited=()))
        self.assertEqual(m.calls, ["cond.1"])

    def test_consistency_reuse_requires_every_cited_block_unchanged(self):
        p = Finding(item_id="consistency.abc", verdict="OPEN — PAGE INCONSISTENT", block=0,
                    cited=["2026 CT5-V vs. 2025 CT5-V Blackwing Comparison | Dealer",
                           "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"])
        self.assertIsNotNone(reuse_prior(p, BLOCKS))
        changed = [BLOCKS[0], blk(1, "2026 CT5-V vs. 2025 CT5-V Blackwing Comparison")]
        self.assertIsNone(reuse_prior(p, changed))

    def test_a_change_in_an_uncited_but_shown_consistency_block_forces_a_fresh_call(self):
        # The Round 2 stale-reuse bug: round 1 cites only the h1, but the title was also shown
        # to the model as a candidate. A regression in the uncited title must not be missed.
        m1 = StubModel({"consistency.abc": {"verdict": "PASS", "reason": "same",
                                            "quotes": ["2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}})
        item = ConsistencyTests().item()
        results = ConsistencyTests().results()
        f1 = judge_item(item, results, BLOCKS, m1)
        self.assertEqual(f1.verdict, "PASS")
        self.assertEqual(f1.cited, ["2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"])
        self.assertIn("2026 CT5-V vs. 2025 CT5-V Blackwing Comparison | Dealer", f1.basis)

        regressed = [blk(0, "2026 CT5-V vs. 2024 CT5-V Blackwing Comparison | Dealer", kind="title")] + BLOCKS[1:]
        m2 = StubModel({"consistency.abc": {"verdict": "INCONSISTENT", "reason": "2024 vs 2026",
                                            "quotes": ["2026 CT5-V vs. 2024 CT5-V Blackwing Comparison | Dealer",
                                                       "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison"]}})
        f2 = judge_item(item, results, regressed, m2, prior=f1)
        self.assertFalse(f2.reused)
        self.assertEqual(m2.calls, ["consistency.abc"])
        self.assertEqual(f2.verdict, "OPEN — PAGE INCONSISTENT")


if __name__ == "__main__":
    unittest.main()
