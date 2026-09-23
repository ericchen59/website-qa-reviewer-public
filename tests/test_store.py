import pathlib
import tempfile
import unittest

from qa_review.schema import Finding, FindingsRecord
from qa_review.store import find_prior, list_runs, load_record, new_run_dir, save_record


def rec(run_id, slug="b"):
    return FindingsRecord(run_id=run_id, baseline={"slug": slug, "hash": "h", "path": "b.md"},
                          page={"key": "p", "kind": "file", "snapshot": "snapshot.html", "styles_vendored": True},
                          findings=[Finding(item_id="a.1", verdict="PASS")])


class StoreTests(unittest.TestCase):
    def test_new_run_dirs_sort_by_time_and_records_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            a = new_run_dir(root, "page-x")
            b = new_run_dir(root, "page-x")
            save_record(a, rec(a.name))
            save_record(b, rec(b.name, slug="other-baseline"))
            self.assertEqual(list_runs(root, "page-x"), [a, b])
            self.assertEqual(load_record(a).run_id, a.name)

    def test_prior_is_the_most_recent_earlier_run_under_any_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            a, b, c = (new_run_dir(root, "p") for _ in range(3))
            save_record(a, rec(a.name, "one")); save_record(b, rec(b.name, "two"))
            save_record(c, rec(c.name, "three"))
            path, r = find_prior(root, "p", current_run_id=c.name)
            self.assertEqual(path, b)
            self.assertEqual(r.baseline["slug"], "two")

    def test_named_prior_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            a, b, c = (new_run_dir(root, "p") for _ in range(3))
            for x in (a, b, c):
                save_record(x, rec(x.name))
            path, _ = find_prior(root, "p", current_run_id=c.name, override=a)
            self.assertEqual(path, a)

    def test_no_prior_for_the_first_run_and_unfinished_runs_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            new_run_dir(root, "p")                # never saved: a coverage error left it empty
            b = new_run_dir(root, "p")
            self.assertIsNone(find_prior(root, "p", current_run_id=b.name))
            self.assertEqual(list_runs(root, "p"), [])


if __name__ == "__main__":
    unittest.main()
