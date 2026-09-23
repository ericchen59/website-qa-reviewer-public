import unittest

from qa_review.ids import item_id, slugify


class IdTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slugify("Page Identity"), "page-identity")
        self.assertEqual(slugify("Key Features — Exterior"), "key-features-exterior")

    def test_same_text_same_id_and_edit_changes_it(self):
        a = item_id("intro", "nearly two decades", 0)
        self.assertEqual(a, item_id("intro", "nearly  two decades", 0))
        self.assertNotEqual(a, item_id("intro", "over two decades", 0))

    def test_typography_does_not_change_id(self):
        self.assertEqual(item_id("s", "you’ll", 0), item_id("s", "you'll", 0))

    def test_ordinal_disambiguates_identical_text(self):
        self.assertNotEqual(item_id("s", "same", 0), item_id("s", "same", 1))

    def test_section_move_changes_id(self):
        self.assertNotEqual(item_id("a", "x", 0), item_id("b", "x", 0))


if __name__ == "__main__":
    unittest.main()
