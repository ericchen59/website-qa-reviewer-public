import unittest

from qa_review.pairing import pair_retired
from qa_review.schema import ChecklistItem


def it(id_, text, section="intro", type_="verbatim"):
    return ChecklistItem(id=id_, section=section, type=type_, text=text)


class PairingTests(unittest.TestCase):
    def test_an_edited_line_is_paired_with_its_replacement(self):
        old = [it("intro.old", "Born and bred, nearly two decades of relentless engineering.")]
        new = [it("intro.new", "Born and bred, over two decades of relentless engineering.")]
        pairs, removed, added = pair_retired(old, new)
        self.assertEqual(pairs, {"intro.old": "intro.new"})
        self.assertEqual((removed, added), ([], []))

    def test_two_equally_good_candidates_are_not_paired(self):
        old = [it("intro.old", "The quick brown fox jumps over the lazy dog today.")]
        new = [it("intro.n1", "The quick brown fox jumps over the lazy dog now."),
               it("intro.n2", "The quick brown fox jumps over the lazy dog soon.")]
        pairs, removed, added = pair_retired(old, new)
        self.assertEqual(pairs, {})
        self.assertEqual(removed, ["intro.old"])
        self.assertEqual(sorted(added), ["intro.n1", "intro.n2"])

    def test_a_deleted_line_is_listed_as_removed(self):
        pairs, removed, added = pair_retired([it("a.1", "Gone entirely from the baseline now")], [])
        self.assertEqual((pairs, removed, added), ({}, ["a.1"], []))

    def test_a_line_moved_to_another_section_is_not_paired(self):
        pairs, removed, added = pair_retired([it("a.1", "Same words in a new place", "a")],
                                             [it("b.1", "Same words in a new place", "b")])
        self.assertEqual(pairs, {})
        self.assertEqual((removed, added), (["a.1"], ["b.1"]))

    def test_dissimilar_text_is_not_paired(self):
        pairs, _, _ = pair_retired([it("a.1", "Alpha beta gamma delta epsilon")],
                                   [it("a.2", "Completely unrelated sentence entirely")])
        self.assertEqual(pairs, {})


if __name__ == "__main__":
    unittest.main()
