#!/usr/bin/env python3
"""
Aggregate convergence results from runs/N*/ directories into tables.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List


def read_run(run_dir: Path) -> Dict[str, float]:
    stats = json.load((run_dir / "stats.json").open())
    count = int((run_dir / "count_result.txt").read_text().strip())
    vars_count = clauses_count = None
    with (run_dir / "model.cnf").open() as f:
        for line in f:
            if line.startswith("p"):
                parts = line.split()
                vars_count = int(parts[2])
                clauses_count = int(parts[3])
                break
    return {
        "probed_pairs": stats["probed_pairs_count"],
        "unique_rules": stats["unique_rule_count"],
        "cnf_vars": vars_count or 0,
        "cnf_clauses": clauses_count or 0,
        "count": count,
        "log10_count": math.log10(count),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate convergence runs.")
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 10, 30, 100])
    args = parser.parse_args()

    rows: List[Dict[str, float]] = []
    prev_count = None
    prev_rules: set | None = None
    for n in args.sizes:
        rd = args.runs / f"N{n}"
        row = read_run(rd)
        row["N"] = n
        # compute deltas
        if prev_count:
            row["ratio_to_prev"] = row["count"] / prev_count
            row["delta_log10"] = row["log10_count"] - math.log10(prev_count)
        else:
            row["ratio_to_prev"] = None
            row["delta_log10"] = None
        rows.append(row)
        prev_count = row["count"]

    # write tables
    table_md = ["|N|probed|(rules)|vars|clauses|count|log10|ratio_to_prev|delta_log10|", "|-|-|-|-|-|-|-|-|"]
    for r in rows:
        ratio = "" if r["ratio_to_prev"] is None else f"{r['ratio_to_prev']:.4g}"
        delta = "" if r["delta_log10"] is None else f"{r['delta_log10']:.4f}"
        table_md.append(
            f"|{r['N']}|{r['probed_pairs']}|{r['unique_rules']}|{r['cnf_vars']}|{r['cnf_clauses']}|{r['count']}|{r['log10_count']:.2f}|{ratio}|{delta}|"
        )
    args.runs.mkdir(parents=True, exist_ok=True)
    (args.runs / "convergence_table.md").write_text("\n".join(table_md), encoding="utf-8")

    import csv

    with (args.runs / "convergence_table.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["N", "probed_pairs", "unique_rules", "cnf_vars", "cnf_clauses", "count", "log10_count", "ratio_to_prev", "delta_log10"],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print("aggregated", len(rows), "runs")


if __name__ == "__main__":
    main()
