import unittest

from qa_review.schema import (
    VERDICTS, ChecklistItem, Finding, FindingsRecord, PageBlock,
)


class SchemaTests(unittest.TestCase):
    def test_six_verdicts(self):
        self.assertEqual(len(VERDICTS), 6)
        self.assertIn("OPEN — PAGE INCONSISTENT", VERDICTS)

    def test_unknown_verdict_raises(self):
        with self.assertRaises(ValueError):
            Finding(item_id="x.1", verdict="MAYBE")

    def test_unknown_item_type_raises(self):
        with self.assertRaises(ValueError):
            ChecklistItem(id="a", section="s", type="weird", text="t")

    def test_record_round_trips_through_json(self):
        rec = FindingsRecord(
            run_id="20260921T120000Z",
            baseline={"slug": "b", "hash": "h", "path": "b.md"},
            page={"key": "p", "kind": "file", "snapshot": "snapshot.html", "styles_vendored": True},
            findings=[
                Finding(item_id="intro.abc123", verdict="FAIL", quote="over two decades",
                        approved_text="nearly two decades", block=3, evidence_hash="e", number=1),
                Finding(item_id="cta.def456", verdict="PASS", quote="View Specials", block=5, evidence_hash="f"),
            ],
            typography_rules=["curly quotes to straight"],
        )
        again = FindingsRecord.from_json(rec.to_json())
        self.assertEqual(again, rec)

    def test_page_block_round_trip(self):
        b = PageBlock(index=0, kind="block", text="Hello", path="body>p", visible="visible",
                      bbox=[1.0, 2.0, 3.0, 4.0])
        self.assertEqual(PageBlock.from_dict(b.to_dict()), b)

    def test_bad_visibility_raises(self):
        with self.assertRaises(ValueError):
            PageBlock(index=0, kind="block", text="x", path="p", visible="maybe")


if __name__ == "__main__":
    unittest.main()
