import contextlib
import io
import json
import pathlib
import shutil
import tempfile
import unittest
import unittest.mock

from qa_review import checks, cli
from qa_review.model import ModelClient
from qa_review.schema import PageBlock
from tests.support import ROOT, intake_stub
from tests.test_visibility import BROWSER

BASELINE = ROOT / "tests" / "data" / "page-baseline.md"
PAGE = ROOT / "tests" / "data" / "pages" / "breadcrumb_table.html"


class TestModel(ModelClient):
    """Intake answered by the intake stub; anything else answers NOT_FOUND."""

    def __init__(self):
        self.intake = intake_stub()

    def ask(self, prompt, schema, label):
        if label == "intake":
            return self.intake.ask(prompt, schema, label)
        return {"verdict": "NOT_FOUND", "quote": "", "reason": "stub"}


def fake_capture(source, run_dir, screenshot=True):
    """A capture with no browser: styles not vendored, so the overlay is skipped too."""
    run_dir = pathlib.Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "snapshot.html").write_text("<html></html>")
    texts = [("Widget Deluxe 2025 | Shop", "title", None), ("Widget Deluxe 2026", "block", None),
             ("Buy now", "block", None), ("Widget", "block", {"table": 0, "row": -1, "col": 0}),
             ("VS", "block", {"table": 0, "row": -1, "col": 1}), ("Widget Pro", "block", {"table": 0, "row": -1, "col": 2}),
             ("$10", "block", {"table": 0, "row": 0, "col": 0}), ("Price*", "block", {"table": 0, "row": 0, "col": 1}),
             ("$20", "block", {"table": 0, "row": 0, "col": 2}), ("Same", "block", {"table": 0, "row": 1, "col": 0}),
             ("Weight", "block", {"table": 0, "row": 1, "col": 1}), ("Same", "block", {"table": 0, "row": 1, "col": 2})]
    blocks = [PageBlock(index=i, kind=k, text=t, path=f"p{i}", visible="visible", table=tb) for i, (t, k, tb) in enumerate(texts)]
    return {"kind": "file", "source": str(source), "key": "sample", "snapshot": "snapshot.html",
            "styles_vendored": False, "notes": [], "blocks": blocks}


def run(*argv, model=None, capture_fn=fake_capture):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv), model=model or TestModel(), capture_fn=capture_fn)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runs = pathlib.Path(tempfile.mkdtemp())
        self.baseline = pathlib.Path(tempfile.mkdtemp()) / "page-baseline.md"
        shutil.copy(BASELINE, self.baseline)

    def review(self, *extra):
        return run("review", str(self.baseline), "sample.html", "--runs", str(self.runs), *extra)

    def confirmed(self):
        self.assertEqual(run("intake", str(self.baseline), "--runs", str(self.runs))[0], 0)
        self.assertEqual(run("confirm", str(self.baseline), "--runs", str(self.runs))[0], 0)

    def test_review_refuses_an_unconfirmed_baseline_and_says_so(self):
        code, out, err = self.review()
        self.assertNotEqual(code, 0)
        self.assertIn("not confirmed", out + err)
        self.assertFalse(list(self.runs.glob("sample/*")))

    def test_intake_prints_the_checklist_and_confirm_then_allows_review(self):
        code, out, _ = run("intake", str(self.baseline), "--runs", str(self.runs))
        self.assertEqual(code, 0)
        self.assertIn("Counts by type", out)
        self.confirmed()
        code, out, err = self.review()
        self.assertEqual(code, 0, out + err)
        self.assertIn("checked:", out)

    def test_changing_one_word_of_the_baseline_invalidates_the_confirmation(self):
        self.confirmed()
        self.baseline.write_text(self.baseline.read_text().replace("Buy now", "Buy today"))
        code, out, err = self.review()
        self.assertNotEqual(code, 0)
        self.assertIn("not confirmed", out + err)

    def test_review_uses_the_frozen_checklist_and_never_reruns_intake(self):
        self.confirmed()
        boom = TestModel()
        boom.intake = None
        code, out, err = self.review()
        self.assertEqual(code, 0, out + err)
        code, out, err = run("review", str(self.baseline), "sample.html", "--runs", str(self.runs), model=boom)
        self.assertEqual(code, 0, out + err)

    def test_intake_on_a_missing_baseline_file_reports_an_error_not_a_traceback(self):
        missing = self.baseline.parent / "does-not-exist.md"
        code, out, err = run("intake", str(missing), "--runs", str(self.runs))
        self.assertEqual(code, 2)
        self.assertIn("can't read baseline", out + err)

    def test_review_on_a_missing_baseline_file_reports_an_error_not_a_traceback(self):
        missing = self.baseline.parent / "does-not-exist.md"
        code, out, err = run("review", str(missing), "sample.html", "--runs", str(self.runs))
        self.assertEqual(code, 2)
        self.assertIn("can't read baseline", out + err)

    def test_a_capture_environment_error_exits_with_its_own_code_and_cleans_up_the_run_dir(self):
        self.confirmed()

        def broken_capture(source, run_dir):
            pathlib.Path(run_dir).mkdir(parents=True, exist_ok=True)
            (pathlib.Path(run_dir) / "partial.html").write_text("<html>")
            raise OSError("Chrome executable not found")

        code, out, err = run("review", str(self.baseline), "sample.html", "--runs", str(self.runs),
                              capture_fn=broken_capture)
        self.assertEqual(code, 3)
        self.assertIn("Chrome executable not found", out + err)
        self.assertFalse(list(self.runs.glob("sample/*")))

    def test_an_unclearable_challenge_exits_with_the_environment_code(self):
        from qa_review.capture import CaptureError
        self.confirmed()

        def challenged_capture(source, run_dir):
            raise CaptureError("the page still looks like a bot-protection challenge after 20s")

        code, out, err = run("review", str(self.baseline), "sample.html", "--runs", str(self.runs),
                              capture_fn=challenged_capture)
        self.assertEqual(code, 3)
        self.assertIn("bot-protection challenge", out + err)

    def test_intake_failure_exits_2_and_writes_no_checklist(self):
        # testing:test_cli.py:98 -- the only existing test hit build_checklist directly; this
        # is the CLI wiring itself: that cmd_intake reports the error, exits 2, and never
        # writes checklist.json (so a later `confirm`/`review` still correctly refuses).
        import qa_review.intake as intake
        real_extract = intake.extract_items

        def dropping(elements):
            items, conds = real_extract(elements)
            return items[:-1], conds

        intake.extract_items = dropping
        try:
            code, out, err = run("intake", str(self.baseline), "--runs", str(self.runs))
        finally:
            intake.extract_items = real_extract
        self.assertEqual(code, 2)
        self.assertIn("count guard", out + err)
        self.assertFalse(list(self.runs.glob("**/checklist.json")))

    def test_review_model_call_error_exits_1_and_removes_the_run_dir(self):
        # testing:test_cli.py:98 -- only CoverageError was ever exercised at the CLI level;
        # cmd_review's ModelCallError branch (delete the run dir, exit 1, no partial report)
        # had no test. Uses a baseline with a judgment condition (page-baseline.md has none,
        # so review never calls the model for it at all) and a model that fails after intake.
        from qa_review.model import ModelCallError
        from tests.support import MINI

        baseline = pathlib.Path(tempfile.mkdtemp()) / "with-condition.md"
        baseline.write_text(MINI)

        class IntakeThenBoom(ModelClient):
            def __init__(self):
                self.intake = intake_stub()

            def ask(self, prompt, schema, label):
                if label == "intake":
                    return self.intake.ask(prompt, schema, label)
                raise ModelCallError("boom: model unavailable")

        m = IntakeThenBoom()
        self.assertEqual(run("intake", str(baseline), "--runs", str(self.runs), model=m)[0], 0)
        self.assertEqual(run("confirm", str(baseline), "--runs", str(self.runs))[0], 0)
        code, out, err = run("review", str(baseline), "sample.html", "--runs", str(self.runs), model=m)
        self.assertEqual(code, 1)
        self.assertIn("boom", out + err)
        self.assertFalse(list(self.runs.glob("sample/*")))   # the run dir was removed, not left partial

    def test_a_coverage_error_exits_nonzero_names_the_item_and_writes_no_report(self):
        self.confirmed()
        real = checks.check_verbatim
        checks.check_verbatim = lambda item, blocks, occ: None if item.text == "Buy now" else real(item, blocks, occ)
        try:
            code, out, err = self.review()
        finally:
            checks.check_verbatim = real
        self.assertNotEqual(code, 0)
        self.assertIn("coverage contract broken", out + err)
        self.assertFalse(list(self.runs.glob("sample/*/report.md")))
        self.assertFalse(list(self.runs.glob("sample/*/findings.json")))

    def test_undervendored_capture_warns_that_visibility_is_degraded(self):
        self.confirmed()
        code, out, err = self.review()  # fake_capture reports styles_vendored=False
        self.assertEqual(code, 0, out + err)
        self.assertIn("styles were not vendored", err)

    def test_fully_vendored_capture_prints_no_degradation_warning(self):
        def vendored_capture(source, run_dir):
            cap = fake_capture(source, run_dir)
            cap["styles_vendored"] = True
            return cap

        self.confirmed()
        code, out, err = run("review", str(self.baseline), "sample.html", "--runs", str(self.runs),
                              capture_fn=vendored_capture)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("styles were not vendored", err)

    def test_review_writes_the_record_report_and_agency_block(self):
        self.confirmed()
        code, out, err = self.review()
        self.assertEqual(code, 0, out + err)
        d = sorted(self.runs.glob("sample/*"))[-1]
        for name in ("findings.json", "report.md", "agency-block.md", "report.html"):
            self.assertTrue((d / name).exists(), name)
        rec = json.loads((d / "findings.json").read_text())
        self.assertEqual(len(rec["findings"]), len(rec["items"]))
        self.assertIn("checked:", (d / "report.md").read_text())

    def test_a_second_review_diffs_against_the_earlier_run(self):
        self.confirmed()
        self.review()
        self.review()
        latest = sorted(self.runs.glob("sample/*"))[-1]
        self.assertIn("## Since the last round", (latest / "report.md").read_text())

    def test_a_named_prior_diffs_against_that_round_not_the_default_most_recent(self):
        # testing:test_cli.py:132 -- with identical reviews, every candidate prior gives the
        # same "nothing changed" diff, so this used to pass whether --prior was honored,
        # ignored, or wrongly passed through as a str (verified: patching store.find_prior to
        # discard override left the old test green). Round 2 diverges from round 1, so diffing
        # round 3 against the explicit --prior (round 1, identical) is provably different from
        # diffing it against the default most-recent (round 2, which would show "Fixed").
        self.confirmed()

        def changing_capture(source, run_dir, _n=[0]):
            _n[0] += 1
            cap = fake_capture(source, run_dir)
            if _n[0] == 2:
                for b in cap["blocks"]:
                    if b.text == "Buy now":
                        b.text = "Buy today"
            return cap

        common = ("review", str(self.baseline), "sample.html", "--runs", str(self.runs))
        self.assertEqual(run(*common, capture_fn=changing_capture)[0], 0)   # round 1: "Buy now"
        first = sorted(self.runs.glob("sample/*"))[0]
        self.assertEqual(run(*common, capture_fn=changing_capture)[0], 0)   # round 2: "Buy today"

        # round 3 ("Buy now" again) diffed against the *named* prior (round 1, identical)
        code, out, err = run(*common, "--prior", str(first), capture_fn=changing_capture)
        self.assertEqual(code, 0, out + err)
        third = sorted(self.runs.glob("sample/*"))[-1]
        report = (third / "report.md").read_text()
        self.assertNotIn("Fixed", report)                      # not "fixed" vs round 1: no change
        self.assertIn("items unchanged and passing", report)   # proving round 1 was actually used

    def test_clean_needs_an_explicit_flag(self):
        code, out, err = run("clean", "--runs", str(self.runs))
        self.assertNotEqual(code, 0)
        self.assertTrue(self.runs.exists())
        self.confirmed()
        self.assertEqual(run("clean", "--runs", str(self.runs), "--all-runs")[0], 0)
        self.assertFalse(self.runs.exists())


class CleanSafetyTests(unittest.TestCase):
    """`clean` must never rmtree a path it doesn't recognize as its own -- see the security
    finding: an unguarded --runs/$QA_REVIEW_RUNS or $QA_REVIEW_PROFILE pointed at the wrong
    directory used to delete whatever was there, ignore_errors=True and all."""

    def setUp(self):
        self.runs = pathlib.Path(tempfile.mkdtemp())
        self.baseline = pathlib.Path(tempfile.mkdtemp()) / "page-baseline.md"
        shutil.copy(BASELINE, self.baseline)

    def confirmed(self):
        self.assertEqual(run("intake", str(self.baseline), "--runs", str(self.runs))[0], 0)
        self.assertEqual(run("confirm", str(self.baseline), "--runs", str(self.runs))[0], 0)

    def test_all_runs_refuses_a_directory_that_is_not_a_runs_store(self):
        (self.runs / "not-ours.txt").write_text("someone else's file")
        code, out, err = run("clean", "--runs", str(self.runs), "--all-runs")
        self.assertNotEqual(code, 0)
        self.assertIn("doesn't look like a qa_review runs store", out + err)
        self.assertTrue(self.runs.exists())
        self.assertTrue((self.runs / "not-ours.txt").exists())

    def test_all_runs_refuses_the_users_home_directory(self):
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "Documents").mkdir()
        with unittest.mock.patch("pathlib.Path.home", return_value=home):
            code, out, err = run("clean", "--runs", str(home), "--all-runs")
        self.assertNotEqual(code, 0)
        self.assertIn("protected system path", out + err)
        self.assertTrue((home / "Documents").exists())

    def test_all_runs_refuses_a_filesystem_root(self):
        code, out, err = run("clean", "--runs", "/", "--all-runs")
        self.assertNotEqual(code, 0)
        self.assertIn("protected system path", out + err)

    def test_all_runs_removes_a_genuine_store_and_says_confirmations_are_cleared(self):
        self.confirmed()
        self.assertEqual(self.review()[0], 0)
        code, out, err = run("clean", "--runs", str(self.runs), "--all-runs")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.runs.exists())
        self.assertIn("baseline confirmations", out)

    def test_all_runs_on_a_missing_root_is_a_harmless_noop(self):
        missing = self.runs / "does-not-exist"
        code, out, err = run("clean", "--runs", str(missing), "--all-runs")
        self.assertEqual(code, 0, out + err)

    def review(self, *extra):
        return run("review", str(self.baseline), "sample.html", "--runs", str(self.runs), *extra)

    def test_profile_refuses_a_directory_with_no_marker(self):
        profile = pathlib.Path(tempfile.mkdtemp())
        (profile / "Default").mkdir()          # looks like *something* important is in here
        with unittest.mock.patch.dict("os.environ", {"QA_REVIEW_PROFILE": str(profile)}):
            code, out, err = run("clean", "--runs", str(self.runs), "--profile")
        self.assertNotEqual(code, 0)
        self.assertIn("no marker file", out + err)
        self.assertTrue(profile.exists())

    def test_profile_removes_a_directory_it_created(self):
        from qa_review.capture import profile_dir
        profile = pathlib.Path(tempfile.mkdtemp()) / "profile"
        with unittest.mock.patch.dict("os.environ", {"QA_REVIEW_PROFILE": str(profile)}):
            profile_dir()                      # this is how the real profile gets created and marked
            self.assertTrue(profile.exists())
            code, out, err = run("clean", "--runs", str(self.runs), "--profile")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(profile.exists())

    def test_profile_refuses_the_users_home_directory(self):
        # e.g. QA_REVIEW_PROFILE mistakenly exported as $HOME -- the exact failure mode
        # the old unguarded rmtree(..., ignore_errors=True) had no defence against.
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "Documents").mkdir()
        with unittest.mock.patch("pathlib.Path.home", return_value=home), \
             unittest.mock.patch.dict("os.environ", {"QA_REVIEW_PROFILE": str(home)}):
            code, out, err = run("clean", "--runs", str(self.runs), "--profile")
        self.assertNotEqual(code, 0)
        self.assertIn("protected system path", out + err)
        self.assertTrue((home / "Documents").exists())


@unittest.skipUnless(BROWSER, "Playwright and Chrome are required")
class EndToEndTests(unittest.TestCase):
    def test_review_of_a_local_page_writes_the_screenshot_and_annotated_report(self):
        runs = pathlib.Path(tempfile.mkdtemp())
        base = pathlib.Path(tempfile.mkdtemp()) / "page-baseline.md"
        shutil.copy(BASELINE, base)
        m = TestModel()
        self.assertEqual(run("intake", str(base), "--runs", str(runs), model=m, capture_fn=None)[0], 0)
        self.assertEqual(run("confirm", str(base), "--runs", str(runs))[0], 0)
        code, out, err = run("review", str(base), str(PAGE), "--runs", str(runs), model=m, capture_fn=None)
        self.assertEqual(code, 0, out + err)
        d = sorted(runs.glob("*/*/findings.json"))[-1].parent
        self.assertTrue((d / "annotated.png").read_bytes().startswith(b"\x89PNG"))
        self.assertIn("data:image/png", (d / "report.html").read_text())
        # the page's tab title says 2025 and its headline 2026: the baseline records both verbatim, so both pass
        self.assertIn("0 FAIL", (d / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
