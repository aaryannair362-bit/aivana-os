"""
Watches tests/scale/results/results.jsonl and writes a per-case PDF (e.g. cases/OPD-00001.pdf)
the moment each new case lands, without needing to touch or restart the runner process that's
writing that file. Backfills any cases already present on startup, then polls for new lines.

Usage:
    python -m tests.scale.case_pdf_watcher [--interval 5]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tests.scale.pdf_report import (  # noqa: E402
    RESULTS_PATH_DEFAULT, CASES_DIR_DEFAULT, load_results, write_case_pdfs_for_new_results,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS_PATH_DEFAULT)
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR_DEFAULT)
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between checks for new cases")
    parser.add_argument("--once", action="store_true", help="Backfill existing results once and exit (no polling)")
    args = parser.parse_args()

    seen = set()
    print(f"Watching {args.results} -> writing per-case PDFs to {args.cases_dir}")
    while True:
        results = load_results(args.results)
        before = len(seen)
        seen = write_case_pdfs_for_new_results(results, args.cases_dir, seen)
        added = len(seen) - before
        if added:
            print(f"Wrote {added} new case PDF(s), {len(seen)} total so far.")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
