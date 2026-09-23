"""Run storage: runs/<page-key>/<UTC timestamp>/ (KTD4).

Runs are keyed by page, so a round-2 run under an edited baseline finds its earlier round;
each record names its own baseline. Everything here is local and gitignored.
"""

from __future__ import annotations

import datetime
import os
import pathlib

from .schema import FindingsRecord

RECORD = "findings.json"


def runs_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("QA_REVIEW_RUNS", "runs"))


def baseline_folder(root, slug: str) -> pathlib.Path:
    return pathlib.Path(root) / slug


def new_run_dir(root, page_key: str) -> pathlib.Path:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    d = pathlib.Path(root) / page_key / stamp
    d.mkdir(parents=True, exist_ok=False)
    return d


def save_record(run_dir, record: FindingsRecord) -> None:
    (pathlib.Path(run_dir) / RECORD).write_text(record.to_json(), encoding="utf-8")


def load_record(run_dir) -> FindingsRecord:
    return FindingsRecord.from_json((pathlib.Path(run_dir) / RECORD).read_text(encoding="utf-8"))


def list_runs(root, page_key: str) -> list[pathlib.Path]:
    """Finished runs for a page, oldest first. A run that never wrote a record is ignored."""
    base = pathlib.Path(root) / page_key
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if (d / RECORD).is_file())


def find_prior(root, page_key: str, current_run_id: str | None = None, override=None):
    """(path, record) of the prior round: the named run, else the most recent earlier finished
    run for this page under any baseline; None for a first run."""
    if override is not None:
        return pathlib.Path(override), load_record(override)
    earlier = [d for d in list_runs(root, page_key) if current_run_id is None or d.name < current_run_id]
    if not earlier:
        return None
    return earlier[-1], load_record(earlier[-1])
