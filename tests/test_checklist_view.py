import unittest

from qa_review.checklist_view import render_view
from qa_review.intake import Checklist
from qa_review.schema import ChecklistItem


def item(id_, text, section="Section", type="verbatim", **kw):
    return ChecklistItem(id=id_, section=section.lower(), section_title=section, type=type,
                         text=text, **kw)


def checklist(items):
    return Checklist(items, {"slug": "s", "path": "p", "hash": "h"},
                     {"applicable": True, "ok": True, "source": {"verbatim": 0, "conditions": 0},
                      "checklist": {"verbatim": 0, "conditions": 0}})


class ViewSubjectsTests(unittest.TestCase):
    def test_a_structural_conditions_subject_is_shown_by_its_own_text(self):
        # adversarial:checklist_view.py:24 -- the model chooses which item a condition binds
        # to; if that choice is wrong, the PMM can only catch it if she can see it.
        subject = item("d.1", "Price excludes tax, dealer fees, title and registration.")
        cond = item("c.1", "The note is visible on page load.", type="structural", subjects=["d.1"])
        view = render_view(checklist([subject, cond]))
        self.assertIn("about: Price excludes tax, dealer fees, title", view)

    def test_a_consistency_checks_refs_and_label_are_shown(self):
        a = item("t.1", "2026 CT5-V vs. 2025 CT5-V Blackwing Comparison")
        b = item("h.1", "2026 CT5-V vs. 2026 CT5-V Blackwing Comparison")
        cons = item("consistency.abc", "The model year is the same everywhere.", type="judgment",
                    refs=["t.1", "h.1"], label="model year")
        view = render_view(checklist([a, b, cons]))
        self.assertIn("'model year' across:", view)
        self.assertIn("2026 CT5-V vs. 2025", view)
        self.assertIn("2026 CT5-V vs. 2026", view)

    def test_a_plain_item_with_no_subjects_or_refs_shows_no_extra_text(self):
        view = render_view(checklist([item("a.1", "Buy now")]))
        self.assertNotIn("about:", view)
        self.assertNotIn("across:", view)


if __name__ == "__main__":
    unittest.main()
