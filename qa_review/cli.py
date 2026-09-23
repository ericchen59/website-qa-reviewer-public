"""Command line: intake, confirm, login, capture, review, vendor, clean.

`review` refuses to run until the PMM has confirmed the frozen checklist for this exact
baseline file, and it never re-runs the intake model (the confirmed checklist is what is reviewed).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

from . import store
from .capture import CaptureError, PROFILE_MARKER, capture, login, page_key, profile_path, vendor_file
from .checklist_view import render_view
from .diff import diff_records
from .ids import slugify
from .intake import IntakeError, build_checklist, confirm, file_hash, is_confirmed, load_frozen, write_checklist
from .model import ClaudeCLIModel, ModelCallError
from .overlay import build_overlay
from .render import assign_numbers, coverage_line, render_agency_block, render_report
from .runner import CoverageError, run_review
from .schema import FindingsRecord


def _root(args) -> pathlib.Path:
    return pathlib.Path(args.runs) if getattr(args, "runs", None) else store.runs_root()


_TIMESTAMP = re.compile(r"^\d{8}T\d{6,}Z$")


def _is_protected_path(path: pathlib.Path) -> bool:
    """Paths `clean` must never remove, no matter what a store/marker check says.

    A misconfigured --runs, $QA_REVIEW_RUNS or $QA_REVIEW_PROFILE can point at anything;
    this is the last line of defence before an rmtree, so it fails closed on any path it
    can't resolve.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return True
    if resolved.parent == resolved:                       # a filesystem root, e.g. "/"
        return True
    if resolved == pathlib.Path.home().resolve():
        return True
    return False


def _looks_like_runs_store(root: pathlib.Path) -> bool:
    """True when every entry directly under `root` is something qa_review would have put
    there: a baseline folder (checklist.json) or a page-key folder of timestamped run dirs.
    A missing or empty root is safe. Anything else -- a stray file, an unrelated directory --
    fails the check, since `--all-runs` must never recurse into a path it doesn't recognize.
    """
    if not root.is_dir():
        return True
    for child in root.iterdir():
        if not child.is_dir():
            return False
        if (child / "checklist.json").is_file():
            continue
        subdirs = [d for d in child.iterdir() if d.is_dir()]
        if subdirs and all(_TIMESTAMP.match(d.name) for d in subdirs):
            continue
        if not any(child.iterdir()):
            continue
        return False
    return True


def _baseline(args):
    """(baseline path, its folder under the runs root, its content hash)."""
    path = pathlib.Path(args.baseline)
    return path, store.baseline_folder(_root(args), slugify(path.stem)), file_hash(path)


def _baseline_or_none(args):
    """`_baseline(args)`, or None with an error already printed for a bad baseline path."""
    try:
        return _baseline(args)
    except OSError as e:
        print(f"error: can't read baseline {args.baseline}: {e}", file=sys.stderr)
        return None


def _capture_exceptions() -> tuple:
    """Environment failures a capture can raise: a missing/broken Chrome, or a bot-protection
    challenge that never cleared (CaptureError). Playwright's own Error is imported lazily so
    commands that never touch a browser don't require it."""
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError:
        return (OSError, CaptureError)
    return (OSError, PlaywrightError, CaptureError)


def _frozen(folder: pathlib.Path, bhash: str):
    try:
        cl = load_frozen(folder)
    except FileNotFoundError:
        return None
    return cl if cl.baseline_hash == bhash else None


def cmd_intake(args, model, capture_fn) -> int:
    found = _baseline_or_none(args)
    if found is None:
        return 2
    path, folder, bhash = found
    cl = _frozen(folder, bhash)
    if cl is None:
        try:
            cl = build_checklist(path, model or ClaudeCLIModel())
        except (IntakeError, ModelCallError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        write_checklist(folder, cl)
    view = render_view(cl)
    (folder / "checklist.md").write_text(view, encoding="utf-8")
    print(view)
    if is_confirmed(folder, cl):
        print("This checklist is confirmed.")
    else:
        print(f"Not confirmed yet. Check the list above, then run: python3 -m qa_review confirm {path}")
    return 0


def cmd_confirm(args, model, capture_fn) -> int:
    found = _baseline_or_none(args)
    if found is None:
        return 2
    _, folder, bhash = found
    if _frozen(folder, bhash) is None:
        print("error: no checklist for this exact baseline; run intake first", file=sys.stderr)
        return 2
    confirm(folder)
    print("Confirmed.")
    return 0


def cmd_capture(args, model, capture_fn) -> int:
    meta = capture_fn(args.source, args.out)
    print(f"captured {meta['source']}: {len(meta['blocks'])} blocks, styles vendored: {meta['styles_vendored']}")
    for n in meta["notes"]:
        print(f"  note: {n}")
    return 0


def cmd_review(args, model, capture_fn) -> int:
    found = _baseline_or_none(args)
    if found is None:
        return 2
    path, folder, bhash = found
    root = _root(args)
    cl = _frozen(folder, bhash)
    if cl is None or not is_confirmed(folder, cl):
        print("error: this baseline is not confirmed. Run intake, check the checklist, then confirm "
              f"(python3 -m qa_review intake {path}).", file=sys.stderr)
        return 2

    key = page_key(args.source)
    run_dir = store.new_run_dir(root, key)
    try:
        cap = capture_fn(args.source, run_dir)
        found = store.find_prior(root, key, current_run_id=run_dir.name, override=args.prior)
        prior_record = found[1] if found else None
        prior_map = {f.item_id: f for f in prior_record.findings} if prior_record else {}
        result = run_review(cl.items, cap["blocks"], model or ClaudeCLIModel(), prior_map)
    except (CoverageError, ModelCallError) as e:
        shutil.rmtree(run_dir, ignore_errors=True)
        print(f"error: {e}", file=sys.stderr)
        return 1
    except _capture_exceptions() as e:
        shutil.rmtree(run_dir, ignore_errors=True)
        print(f"error: {e}", file=sys.stderr)
        return 3

    record = FindingsRecord(
        run_id=run_dir.name, baseline=dict(cl.baseline),
        page={"key": key, "kind": cap["kind"], "snapshot": "snapshot.html",
              "styles_vendored": cap["styles_vendored"], "source": args.source},
        findings=result.findings, typography_rules=result.typography_rules, items=cl.items)
    assign_numbers(record)
    store.save_record(run_dir, record)
    diff = diff_records(prior_record, record)
    (run_dir / "report.md").write_text(render_report(record, diff), encoding="utf-8")
    (run_dir / "agency-block.md").write_text(render_agency_block(record), encoding="utf-8")
    build_overlay(record, cap["blocks"], run_dir / "snapshot.html", run_dir)
    if not cap["styles_vendored"]:
        print("warning: page styles were not vendored; visibility checks and the annotated "
              "screenshot are degraded", file=sys.stderr)
        for n in cap.get("notes", []):
            print(f"  note: {n}", file=sys.stderr)
    print(coverage_line(record))
    print(f"Report:        {run_dir / 'report.md'}")
    print(f"Agency block:  {run_dir / 'agency-block.md'}")
    print(f"Annotated:     {run_dir / 'report.html'}")
    return 0


def cmd_login(args, model, capture_fn) -> int:
    login(args.url)
    print("session saved to the browser profile")
    return 0


def cmd_vendor(args, model, capture_fn) -> int:
    ok, notes = vendor_file(args.html, args.out, args.base_url)
    print(f"wrote {args.out}; styles vendored: {ok}")
    for n in notes:
        print(f"  note: {n}")
    return 0 if ok else 1


def cmd_clean(args, model, capture_fn) -> int:
    if not (args.profile or args.all_runs):
        print("error: say what to remove: --profile (browser login) and/or --all-runs", file=sys.stderr)
        return 2
    if args.profile:
        p = profile_path()
        if _is_protected_path(p):
            print(f"error: refusing to remove {p}: it resolves to a protected system path. "
                  "Check $QA_REVIEW_PROFILE.", file=sys.stderr)
            return 2
        if p.exists() and not (p / PROFILE_MARKER).is_file():
            print(f"error: refusing to remove {p}: it doesn't look like a qa_review browser "
                  "profile (no marker file). Check $QA_REVIEW_PROFILE.", file=sys.stderr)
            return 2
        if p.exists():
            shutil.rmtree(p)
        print("removed the browser profile")
    if args.all_runs:
        root = _root(args)
        if _is_protected_path(root):
            print(f"error: refusing to remove {root}: it resolves to a protected system path. "
                  "Check --runs / $QA_REVIEW_RUNS.", file=sys.stderr)
            return 2
        if not _looks_like_runs_store(root):
            print(f"error: refusing to remove {root}: it doesn't look like a qa_review runs "
                  "store (unexpected contents). Check --runs / $QA_REVIEW_RUNS.", file=sys.stderr)
            return 2
        if root.exists():
            shutil.rmtree(root)
        print("removed all runs (this also clears baseline confirmations under this root -- "
              "re-run intake and confirm before reviewing again)")
    return 0


def main(argv=None, model=None, capture_fn=None) -> int:
    ap = argparse.ArgumentParser(prog="qa_review", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *positional, runs=True):
        p = sub.add_parser(name)
        for a in positional:
            p.add_argument(a)
        if runs:
            p.add_argument("--runs", help="runs folder (default: runs/ or $QA_REVIEW_RUNS)")
        p.set_defaults(fn=fn)
        return p

    add("intake", cmd_intake, "baseline")
    add("confirm", cmd_confirm, "baseline")
    add("login", cmd_login, "url", runs=False)
    add("capture", cmd_capture, "source", "out", runs=False)
    add("review", cmd_review, "baseline", "source").add_argument("--prior", help="an earlier run folder to diff against")
    v = add("vendor", cmd_vendor, "html", "out", runs=False)
    v.add_argument("--base-url", required=True, help="the URL the saved page was captured from")
    c = add("clean", cmd_clean)
    c.add_argument("--profile", action="store_true", help="remove the saved browser login")
    c.add_argument("--all-runs", action="store_true", help="remove every stored run")

    args = ap.parse_args(argv)
    return args.fn(args, model, capture_fn or capture)
