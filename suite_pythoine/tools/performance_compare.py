"""Compare opt-in Wave-1 traces without claiming results from missing GUI runs.

Use a merged or repeated --log JSONL file captured with SUITE_PYTHOINE_PERF=1.
A minimum number of measurements per operation/version is required; partial
runs are explicitly marked incomplete rather than silently treated as parity.
This tool never launches Qt or modifies the Suite installation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median
import sys

DEFAULT_OPERATIONS = (
    "startup", "refresh_editors", "inventory_discovery",
    "page_installed_applications", "page_application", "page_version_history",
    "page_catalogue", "page_catalog_component",
)


def _percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * .95) - 1]


def read_traces(paths: list[Path]) -> list[dict]:
    records = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for lineno, raw in enumerate(stream, 1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except ValueError as exc:
                    raise ValueError(f"{path}:{lineno}: invalid JSONL ({exc})") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{lineno}: not a trace object")
                records.append(value)
    return records


def compare_records(records: list[dict], baseline: str, candidate: str,
                    operations: tuple[str, ...] = DEFAULT_OPERATIONS,
                    min_samples: int = 5) -> tuple[list[dict], list[str]]:
    if baseline == candidate:
        raise ValueError("baseline and candidate must be different version identities")
    if min_samples < 1:
        raise ValueError("min_samples must be positive")
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in records:
        version = row.get("suite_version")
        operation = row.get("operation")
        duration = row.get("total_ms")
        if (version not in (baseline, candidate) or operation not in operations
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or not math.isfinite(duration) or duration < 0):
            continue
        groups[version, operation].append(float(duration))
    report: list[dict] = []
    incomplete: list[str] = []
    for operation in operations:
        before = groups[baseline, operation]
        after = groups[candidate, operation]
        if len(before) < min_samples or len(after) < min_samples:
            incomplete.append(f"{operation}: baseline={len(before)}, candidate={len(after)}, minimum={min_samples}")
            continue
        b = median(before)
        c = median(after)
        report.append({
            "operation": operation,
            "baseline_n": len(before), "candidate_n": len(after),
            "baseline_median_ms": round(b, 3), "candidate_median_ms": round(c, 3),
            "baseline_p95_ms": round(_percentile95(before), 3),
            "candidate_p95_ms": round(_percentile95(after), 3),
            "median_ratio": round(c / b, 3) if b else None,
        })
    return report, incomplete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, action="append", required=True,
                        help="one or more traces; may contain multiple Suite versions")
    parser.add_argument("--baseline-version", default="1.0.0-x1.0")
    parser.add_argument("--candidate-version", default="1.0.0-x1.6")
    parser.add_argument("--min-samples", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        results, missing = compare_records(
            read_traces(args.log), args.baseline_version, args.candidate_version,
            min_samples=args.min_samples)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"BASELINE {args.baseline_version} | CANDIDATE {args.candidate_version}")
    for item in results:
        ratio = item["median_ratio"]
        label = f"{ratio}x" if ratio is not None else "n/a (zero baseline)"
        print(f"{item['operation']}: median {item['baseline_median_ms']} -> "
              f"{item['candidate_median_ms']} ms ({label}); "
              f"p95 {item['baseline_p95_ms']} -> {item['candidate_p95_ms']} ms; "
              f"n={item['baseline_n']}/{item['candidate_n']}")
    if missing:
        for entry in missing:
            print(f"INCOMPLETE: {entry}")
        print("No overall performance-parity claim: more comparable GUI traces needed.")
        return 2
    print("COMPLETE: data coverage sufficient; inspect ratios for regressions (no automatic parity claim).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
