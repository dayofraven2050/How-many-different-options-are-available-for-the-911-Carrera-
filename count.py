#!/usr/bin/env python3
"""
Compile CNF to SDD and count satisfying assignments (exact #SAT).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from pysdd.sdd import SddManager, WmcManager


def load_cnf(path: Path) -> (int, List[List[int]]):
    clauses: List[List[int]] = []
    num_vars = 0
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                parts = line.split()
                num_vars = int(parts[2])
                continue
            lits = [int(x) for x in line.split() if x != "0"]
            if lits:
                clauses.append(lits)
    return num_vars, clauses


def count_models(num_vars: int, clauses: List[List[int]]) -> int:
    mgr = SddManager(var_count=num_vars)
    node = mgr.true()
    for clause in clauses:
        disj = mgr.false()
        for lit in clause:
            disj = mgr.disjoin(disj, mgr.literal(lit))
        node = mgr.conjoin(node, disj)
    wmc = WmcManager(node, log_mode=False)
    return int(wmc.propagate())


def main() -> None:
    parser = argparse.ArgumentParser(description="Count models of data/model.cnf using pysdd.")
    parser.add_argument("--cnf", type=Path, default=Path("data/model.cnf"))
    parser.add_argument("--out", type=Path, default=Path("data/count_result.txt"))
    args = parser.parse_args()

    num_vars, clauses = load_cnf(args.cnf)
    count = count_models(num_vars, clauses)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(str(count), encoding="utf-8")
    print(f"model count: {count}")


if __name__ == "__main__":
    main()
