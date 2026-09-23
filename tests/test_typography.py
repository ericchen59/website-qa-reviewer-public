import unittest

from qa_review.typography import normalize, normalize_with_rules


class TypographyTests(unittest.TestCase):
    def test_curly_quotes_fold_to_straight(self):
        self.assertEqual(normalize("You’ll learn “all”"), "You'll learn \"all\"")

    def test_nbsp_becomes_space_and_runs_collapse(self):
        self.assertEqual(normalize("a  b   c\n d"), "a b c d")

    def test_meaningful_punctuation_is_never_normalized(self):
        self.assertNotEqual(normalize("Starting MSRP*"), normalize("Starting MSRP"))
        self.assertNotEqual(normalize("CT5-V vs. CT5-V"), normalize("CT5-V vs CT5-V"))
        self.assertNotEqual(normalize("a – b"), normalize("a - b"))
        self.assertNotEqual(normalize("Head-Up"), normalize("head-up"))
        self.assertNotEqual(normalize("price†"), normalize("price"))

    def test_applied_rules_name_only_rules_that_changed_something(self):
        _, rules = normalize_with_rules("plain text")
        self.assertEqual(rules, [])
        _, rules = normalize_with_rules("it’s")
        self.assertEqual(rules, ["curly quotes to straight"])
        _, rules = normalize_with_rules("a b  c")
        self.assertIn("non-breaking space to space", rules)
        self.assertIn("whitespace collapsed", rules)

    def test_strips_outer_whitespace(self):
        self.assertEqual(normalize("  x \n"), "x")


if __name__ == "__main__":
    unittest.main()
