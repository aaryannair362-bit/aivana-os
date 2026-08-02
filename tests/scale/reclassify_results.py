"""
One-time correction pass: recomputes each recorded result's pass/fail `status` using the
corrected logic (a case where every real-transcript visit failed to produce a prescription
used to be silently left as "pass" -- see runner.py's run_scenario for the full explanation).
Rewrites results.jsonl in place so the stored data is accurate, not just the report.

Regenerates each scenario deterministically from its test_id (the generator is seeded by
test_id) to know how many visits actually needed a real prescription, without requiring any
extra data to have been stored at run time.

Usage:
    python -m tests.scale.reclassify_results
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tests.scale.scenario_generator import generate_scenario  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "results.jsonl"


def expected_visit_count(test_id: str) -> int:
    category, seq_str = test_id.rsplit("-", 1)
    scenario = generate_scenario(category, int(seq_str))
    return sum(1 for v in scenario.visits if len(" ".join(v)) >= 10)


def recompute_status(result: dict) -> dict:
    """Only ever upgrades pass -> fail against the corrected criteria; never downgrades an
    existing fail back to pass. A case already marked failed (JS error, concurrent-task-race
    server error, missing interaction warning, etc.) keeps that verdict regardless -- this
    pass is specifically about the one criterion that was missing (total/partial visit
    failure), not a full re-judgment that could accidentally erase a different real failure."""
    if result.get("status") == "fail":
        return result

    expected = expected_visit_count(result["test_id"])
    failed_visits = sum(1 for n in (result.get("notes") or []) if re.match(r"^visit \d+:", n))

    if expected > 0 and failed_visits >= expected:
        result["status"] = "fail"
        result["error"] = f"all {expected} visit(s) with a real transcript failed to produce a prescription"
    elif expected > 0 and failed_visits > 0:
        result["status"] = "fail"
        result["error"] = f"{failed_visits} of {expected} visit(s) failed to produce a prescription"
    return result


def main():
    if not RESULTS_PATH.exists():
        print(f"No results file at {RESULTS_PATH}")
        return

    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    changed = 0
    for result in lines:
        before = (result.get("status"), result.get("error"))
        recompute_status(result)
        if (result.get("status"), result.get("error")) != before:
            changed += 1
            print(f"  {result['test_id']}: {before[0]} -> {result['status']} ({result.get('error')})")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        for result in lines:
            f.write(json.dumps(result) + "\n")

    print(f"Reclassified {len(lines)} results, {changed} status(es) changed.")


if __name__ == "__main__":
    main()
