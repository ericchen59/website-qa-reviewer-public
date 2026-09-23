import pathlib
import tempfile
import unittest
import zipfile

from qa_review.docx_reader import raw_counts, read_docx
from qa_review.intake import read_markdown
from tests.support import BASELINE, to_docx

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# A real Word round-trip stamps rsid/paraId attributes on nearly every element -- md2docx.py's
# own output never does, so the existing fixtures can't exercise this. adversarial:docx_reader.py:100.
_ATTR_BEARING_DOC = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}">
<w:body>
<w:p w:rsidR="00A2" w:rsidRDefault="00A2">
<w:pPr><w:pBdr w:rsidR="00A2"><w:left w:val="single" w:sz="4"/></w:pBdr></w:pPr>
<w:r><w:t>A boxed quote</w:t></w:r>
</w:p>
<w:p w:rsidR="00A3" w:rsidRDefault="00A3">
<w:r><w:t>1. A numbered condition</w:t></w:r>
</w:p>
<w:tbl w:rsidR="00A4">
<w:tr w:rsidR="00A4"><w:trPr><w:tblHeader/></w:trPr><w:tc><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:tc></w:tr>
<w:tr w:rsidR="00A4"><w:tc><w:p><w:r><w:t>Cell one</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
</w:body>
</w:document>"""


def _write_docx(xml: str, path) -> pathlib.Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    return path


class DocxReaderTests(unittest.TestCase):
    def test_raw_counts_matches_attribute_bearing_paragraphs_not_just_bare_ones(self):
        with tempfile.TemporaryDirectory() as d:
            docx = _write_docx(_ATTR_BEARING_DOC, pathlib.Path(d) / "attr.docx")
            counts = raw_counts(docx)
        # a boxed quote (1 verbatim) + one table cell counted (header row excluded) + one condition
        self.assertEqual(counts, {"verbatim": 2, "conditions": 1})

    def test_a_real_word_round_trip_is_not_reported_as_an_empty_baseline(self):
        from qa_review.intake import build_checklist
        from tests.support import intake_stub
        with tempfile.TemporaryDirectory() as d:
            docx = _write_docx(_ATTR_BEARING_DOC, pathlib.Path(d) / "attr.docx")
            cl = build_checklist(docx, intake_stub())
        self.assertTrue(cl.guard["applicable"])
        self.assertEqual(len(cl.items), 3)   # the boxed quote, the table cell, the condition

    def test_extraction_finding_items_with_a_blind_raw_pass_fails_loud_not_silent(self):
        # Defense in depth: even if some future guard blind spot slips through, "extraction
        # found real items but the independent pass found none" must never read as an
        # empty/not-applicable baseline.
        import qa_review.docx_reader as docx_reader
        from qa_review.intake import IntakeError, build_checklist
        from tests.support import intake_stub
        real = docx_reader.raw_counts
        docx_reader.raw_counts = lambda path: {"verbatim": 0, "conditions": 0}
        try:
            with tempfile.TemporaryDirectory() as d:
                docx = _write_docx(_ATTR_BEARING_DOC, pathlib.Path(d) / "attr.docx")
                with self.assertRaises(IntakeError) as cm:
                    build_checklist(docx, intake_stub())
            self.assertIn("count-guard bug", str(cm.exception))
        finally:
            docx_reader.raw_counts = real

    def test_docx_elements_match_markdown_elements(self):
        with tempfile.TemporaryDirectory() as d:
            docx = to_docx(BASELINE, pathlib.Path(d) / "b.docx")
            md = read_markdown(BASELINE.read_text(encoding="utf-8"))
            dx = read_docx(docx)

        def sig(els):
            from qa_review.typography import normalize
            return [(e.kind, normalize(e.text), e.table, e.row, e.col) for e in els
                    if e.kind in ("quote", "cell", "header_cell", "condition", "section")]

        self.assertEqual(sig(dx), sig(md))

    def test_docx_recovers_boxed_quotes_and_conditions(self):
        with tempfile.TemporaryDirectory() as d:
            els = read_docx(to_docx(BASELINE, pathlib.Path(d) / "b.docx"))
        self.assertEqual(sum(e.kind == "quote" for e in els), 15)
        self.assertEqual(sum(e.kind == "condition" for e in els), 5)


if __name__ == "__main__":
    unittest.main()
