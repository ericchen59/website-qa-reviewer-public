import os
import pathlib
import unittest

from qa_review.diff import diff_records
from qa_review.render import assign_numbers, render_agency_block, render_report
from qa_review.schema import ChecklistItem, Finding, FindingsRecord

GOLDEN = pathlib.Path(__file__).parent / "golden"


def item(id_, text, section="Section"):
    return ChecklistItem(id=id_, section=section.lower(), section_title=section, type="verbatim", text=text)


def find(id_, verdict, approved="", quote="", **kw):
    return Finding(item_id=id_, verdict=verdict, approved_text=approved, quote=quote, **kw)


def record(findings, rules=("curly quotes to straight",), run_id="20260921T120000000000Z"):
    items = [item(f.item_id, f.approved_text or "x") for f in findings]
    return FindingsRecord(run_id=run_id, baseline={"slug": "sample-baseline", "hash": "abcdef123456", "path": "b.md"},
                          page={"key": "sample-page", "kind": "file", "snapshot": "snapshot.html", "styles_vendored": True},
                          findings=findings, typography_rules=list(rules), items=items)


def pristine():
    return record([find("a.1", "PASS", "One", "One"), find("a.2", "PASS", "Two", "Two"),
                   find("c.1", "OPEN — PAGE INCONSISTENT", "Model year is 2026 everywhere",
                        "2026 X vs. 2025 X | 2026 X vs. 2026 X", explanation="years differ")])


def rebuild():
    return record([
        find("i.1", "FAIL", "nearly two decades", "over two decades", explanation='approved "nearly" but page has "over"'),
        find("s.1", "FAIL", "$57,600", "$58,900", explanation='approved "$57,600" but page has "$58,900"'),
        find("s.2", "FAIL", "Starting MSRP*", "Starting MSRP", explanation='approved "MSRP*" but page has "MSRP"'),
        find("e.1", "FAIL", "finishes that include polished silver", "three finishes: polished silver"),
        find("d.1", "FAIL", "*Price excludes tax, dealer fees.", "*Price excludes tax."),
        find("d.5", "FAIL", "visible on load", "*Price excludes tax.", explanation="present but not visible on page load"),
        find("a.1", "PASS", "One", "One"), find("a.2", "PASS", "Two", "Two"), find("a.3", "PASS", "Three", "Three"),
        find("c.1", "OPEN — PAGE INCONSISTENT", "Model year is 2026 everywhere", "2026 vs 2025", explanation="years differ")])


class ReportTests(unittest.TestCase):
    def test_coverage_line_counts_sum_to_the_total_for_both_shapes(self):
        for rec, line in ((pristine(), "3/3 checked: 2 PASS, 0 FAIL, 0 WARN, 0 NOT FOUND, 1 OPEN"),
                          (rebuild(), "10/10 checked: 3 PASS, 6 FAIL, 0 WARN, 0 NOT FOUND, 1 OPEN")):
            assign_numbers(rec)
            self.assertEqual(render_report(rec, None).split("\n")[2].strip("*"), line)

    def test_open_verdicts_go_to_the_marketing_list_not_the_agency_block(self):     # AE4
        rec = rebuild()
        assign_numbers(rec)
        self.assertIn("## Open items for Marketing", render_report(rec, None))
        self.assertNotIn("2026 vs 2025", render_agency_block(rec))
        self.assertNotIn("c.1", render_agency_block(rec))

    def test_agency_block_does_not_say_no_differences_when_items_still_need_a_look(self):
        # adversarial:render.py:176 -- a review where every non-PASS finding is a check-by-eye
        # WARN or an OPEN item has zero agency-facing rows, but that isn't "no differences":
        # it's unresolved, and the pasteable block must not say otherwise.
        rec = record([find("a.1", "PASS", "x", "x"),
                      find("w.1", "WARN", "visible on load", "text", check_by_eye=True),
                      find("o.1", "OPEN — PAGE INCONSISTENT", "y", "z")])
        assign_numbers(rec)
        block = render_agency_block(rec)
        self.assertNotIn("found no differences.", block)
        self.assertIn("still need", block)
        self.assertIn("open item", block)

    def test_agency_block_says_no_differences_only_when_truly_clean(self):
        rec = record([find("a.1", "PASS", "x", "x"), find("a.2", "PASS", "y", "y")])
        assign_numbers(rec)
        self.assertIn("found no differences.", render_agency_block(rec))

    def test_not_found_is_in_the_table_and_the_agency_block(self):
        rec = record([find("a.1", "NOT FOUND ON PAGE", "Some approved copy", "")])
        assign_numbers(rec)
        self.assertIn("NOT FOUND", render_report(rec, None).split("## Open items")[0])
        self.assertIn("Some approved copy", render_agency_block(rec))

    def test_undetermined_visibility_warning_is_counted_but_listed_only_under_check_by_eye(self):
        rec = record([find("a.1", "WARN", "visible on load", "text", check_by_eye=True),
                      find("a.2", "PASS", "x", "x")])
        assign_numbers(rec)
        rep = render_report(rec, None)
        self.assertIn("1 WARN", rep)
        table = rep.split("## Findings for the agency")[1].split("##")[0]
        self.assertNotIn("a.1", table)
        self.assertIn("## Check by eye", rep)
        self.assertIn("a.1", rep.split("## Check by eye")[1])
        self.assertNotIn("a.1", render_agency_block(rec))

    def test_report_names_the_typography_rules_applied(self):
        rec = pristine()
        assign_numbers(rec)
        self.assertIn("curly quotes to straight", render_report(rec, None))

    def test_one_number_sequence_across_the_lists(self):
        rec = record([find("f.1", "FAIL", "a", "b"), find("o.1", "OPEN — NEEDS MARKETING", "c", "d"),
                      find("w.1", "WARN", "e", "f", check_by_eye=True)])
        assign_numbers(rec)
        self.assertEqual({f.item_id: f.number for f in rec.findings}, {"f.1": 1, "o.1": 2, "w.1": 3})

    def test_markdown_syntax_in_quotes_is_escaped_in_the_report_and_neutralized_in_the_agency_block(self):
        evil = "[click](http://evil.example) <script>x</script> | pipe `tick`"
        rec = record([find("a.1", "FAIL", "Approved", evil)])
        assign_numbers(rec)
        rep = render_report(rec, None)
        self.assertNotIn("[click](http", rep)
        self.assertNotIn("<script>", rep)
        agency = render_agency_block(rec)
        self.assertNotIn("](http", agency)

    def test_agency_block_matches_golden(self):
        rec = rebuild()
        assign_numbers(rec)
        self.check_golden("agency-rebuild.txt", render_agency_block(rec))

    def test_report_matches_golden(self):
        rec = rebuild()
        assign_numbers(rec)
        self.check_golden("report-rebuild.md", render_report(rec, None))

    def check_golden(self, name, text):
        # testing:test_render.py:110 -- writing on a missing file meant a deleted or never-
        # committed golden turned green instead of failing, and silently rewrote tracked
        # files for anyone whose checkout lacked one. Only UPDATE_GOLDEN=1 may write now.
        path = GOLDEN / name
        if os.environ.get("UPDATE_GOLDEN"):
            path.write_text(text, encoding="utf-8")
        elif not path.exists():
            self.fail(f"golden file missing: {path}; run with UPDATE_GOLDEN=1 to create it")
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_a_missing_golden_fails_loud_instead_of_being_silently_created(self):
        missing = GOLDEN / "does-not-exist-nobody-should-create-this.txt"
        self.assertFalse(missing.exists())
        try:
            with self.assertRaises(AssertionError):
                self.check_golden(missing.name, "some text")
            self.assertFalse(missing.exists())    # and it must still not exist afterward
        finally:
            missing.unlink(missing_ok=True)       # in case a regression did create it


class RoundTwoTests(unittest.TestCase):
    def rounds(self):
        old = "Born and bred, nearly two decades of relentless engineering."
        new = "Born and bred, over two decades of relentless engineering."
        p = record([find("i.old", "FAIL", old, "over two decades", evidence_hash="e1", cited=["e1"]),
                    find("a.1", "PASS", "One", "One", evidence_hash="a", cited=["a"])], run_id="20260921T110000000000Z")
        c = record([find("i.new", "PASS", new, "over two decades", evidence_hash="e1", cited=["e1"]),
                    find("a.1", "PASS", "One", "One", evidence_hash="a", cited=["a"])])
        c.items[0].section = p.items[0].section = "intro"
        return p, c

    def test_replaced_id_shows_dagger_in_the_diff_and_a_footnote_with_both_texts(self):   # AE3
        p, c = self.rounds()
        assign_numbers(c)
        rep = render_report(c, diff_records(p, c))
        self.assertIn("## Since the last round", rep)
        self.assertIn("`i.new`† replaces `i.old`", rep)
        self.assertIn("nearly two decades", rep.split("## Footnotes")[1])
        self.assertIn("over two decades", rep.split("## Footnotes")[1])
        self.assertNotIn("fixed", rep.lower().split("## since the last round")[1].split("## footnotes")[0].replace("unchanged", ""))

    def test_a_failing_replaced_id_carries_the_dagger_in_the_table_without_a_new_column(self):
        p, c = self.rounds()
        c.findings[0].verdict = "FAIL"
        assign_numbers(c)
        table = render_report(c, diff_records(p, c)).split("## Findings for the agency")[1].split("##")[0]
        self.assertIn("i.new†", table)
        self.assertEqual(table.strip().splitlines()[0].count("|"), 6)     # #, ID, severity, page, approved

    def test_agency_block_never_carries_the_dagger(self):
        p, c = self.rounds()
        c.findings[0].verdict = "FAIL"
        assign_numbers(c)
        self.assertNotIn("†", render_agency_block(c))

    def test_removed_lines_are_listed_in_the_footnotes(self):
        p, c = self.rounds()
        p.findings.append(find("gone.1", "PASS", "Removed copy line entirely", "x", evidence_hash="z", cited=["z"]))
        p.items.append(item("gone.1", "Removed copy line entirely"))
        assign_numbers(c)
        rep = render_report(c, diff_records(p, c))
        self.assertIn("Removed from approved copy", rep)
        self.assertIn("Removed copy line entirely", rep)


if __name__ == "__main__":
    unittest.main()


class ExcerptTests(unittest.TestCase):
    LONG = ("Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa "
            "quebec romeo sierra tango uniform victor whiskey xray yankee zulu " * 3)

    def test_short_texts_are_unchanged(self):
        from qa_review.render import excerpt_pair
        self.assertEqual(excerpt_pair("over two", "nearly two"), ("over two", "nearly two"))

    def test_a_long_paragraph_is_cut_to_the_changed_words_with_context(self):
        from qa_review.render import excerpt_pair
        approved = self.LONG.replace("mike", "MIKE-APPROVED", 1)
        page = self.LONG.replace("mike", "MIKE-PAGE", 1)
        p, a = excerpt_pair(page, approved)
        self.assertIn("MIKE-PAGE", p)
        self.assertIn("MIKE-APPROVED", a)
        self.assertLess(len(p), 220)
        self.assertLess(len(a), 220)
        self.assertTrue(p.startswith("…") and p.endswith("…"))

    def test_a_missing_long_paragraph_is_truncated(self):
        from qa_review.render import excerpt_pair
        p, a = excerpt_pair("", self.LONG)
        self.assertEqual(p, "")
        self.assertLessEqual(len(a), 221)

    def test_report_and_agency_block_use_excerpts_for_long_text(self):
        approved = self.LONG.replace("mike", "MIKE-APPROVED", 1)
        page = self.LONG.replace("mike", "MIKE-PAGE", 1)
        rec = record([find("a.1", "FAIL", approved, page)])
        assign_numbers(rec)
        self.assertLess(len(render_report(rec, None)), 1200)
        self.assertLess(len(render_agency_block(rec)), 800)
        self.assertIn("MIKE-PAGE", render_agency_block(rec))
