#!/usr/bin/env python3
"""
Build DIMACS CNF model for Porsche 911 (9921B2) configurator.

Uses:
- data/options.csv (from parse_har.py)
- data/constraints.json (from probe_rules.py)
- data/feasibility_from_har.json (HAR change sets)

Outputs:
- data/model.cnf
- data/varmap.json (optionId -> dimacs var id)
- data/required_families.json (for reporting)
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def load_options(path: Path) -> List[Dict[str, Any]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_constraints(paths: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        if not p.exists():
            continue
        out.extend(json.load(p.open()))
    return out


def at_most_one(vars_: List[int]) -> List[List[int]]:
    clauses = []
    for i in range(len(vars_)):
        for j in range(i + 1, len(vars_)):
            clauses.append([-vars_[i], -vars_[j]])
    return clauses


def build_cnf(
    options: List[Dict[str, Any]],
    constraints: List[Dict[str, Any]],
    banned: Set[str],
    out_cnf: Path,
    out_varmap: Path,
    out_required: Path,
) -> None:
    # filter: exclude tequipment
    countable = [o for o in options if o.get("equipmentType") != "tequipment"]
    opt_lookup = {o["optionId"]: o for o in countable}

    varmap: Dict[str, int] = {}
    for opt in countable:
        oid = opt["optionId"]
        varmap[oid] = len(varmap) + 1

    # family constraints
    fam_map: Dict[str, List[str]] = {}
    for opt in countable:
        fam = opt.get("family") or ""
        fam_map.setdefault(fam, []).append(opt["optionId"])

    clauses: List[List[int]] = []
    # fixed truth values for standard equipment (only when no alternatives) / banned
    for opt in countable:
        oid = opt["optionId"]
        vid = varmap[oid]
        fam = opt.get("family") or ""
        if oid in banned:
            clauses.append([-vid])
        elif opt.get("isStandardEquipment") == "True" and len(fam_map.get(fam, [])) <= 1:
            clauses.append([vid])

    required_families: List[str] = []
    for fam, members in fam_map.items():
        real_members = [m for m in members if m in varmap and m not in banned]
        if fam and len(real_members) > 1:
            clauses.extend(at_most_one([varmap[m] for m in real_members]))
        if any(
            opt_lookup.get(m, {}).get("isStandardEquipment") == "True"
            or opt_lookup.get(m, {}).get("isSelected") == "True"
            for m in members
        ):
            required_families.append(fam or "<none>")
            pos = [varmap[m] for m in real_members]
            if pos:
                clauses.append(pos)

    # implication constraints from feasibility probes
    for rec in constraints:
        o_add = rec.get("optionAdded")
        if not o_add or o_add not in varmap:
            continue
        v_add = varmap[o_add]
        for a in rec.get("engineAddedOptions", []) or []:
            if a in varmap and a not in banned:
                clauses.append([-v_add, varmap[a]])
        for r in rec.get("removedOptions", []) or []:
            if r in varmap and r not in banned:
                clauses.append([-v_add, -varmap[r]])

    out_cnf.parent.mkdir(parents=True, exist_ok=True)
    out_varmap.parent.mkdir(parents=True, exist_ok=True)

    with out_cnf.open("w", encoding="utf-8") as f:
        f.write(f"p cnf {len(varmap)} {len(clauses)}\n")
        for c in clauses:
            f.write(" ".join(str(lit) for lit in c) + " 0\n")

    with out_varmap.open("w", encoding="utf-8") as f:
        json.dump(varmap, f, ensure_ascii=False, indent=2)

    with out_required.open("w", encoding="utf-8") as f:
        json.dump(sorted(required_families), f, ensure_ascii=False, indent=2)

    print(f"vars: {len(varmap)}, clauses: {len(clauses)}")
    print(f"required families: {len(required_families)} written to {out_required}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DIMACS CNF from parsed options and feasibility probes.")
    parser.add_argument("--options", type=Path, default=Path("data/options.csv"))
    parser.add_argument("--constraints", type=Path, default=Path("data/constraints.json"))
    parser.add_argument("--har-constraints", type=Path, default=Path("data/feasibility_from_har.json"))
    parser.add_argument("--out-cnf", type=Path, default=Path("data/model.cnf"))
    parser.add_argument("--out-varmap", type=Path, default=Path("data/varmap.json"))
    parser.add_argument("--out-required", type=Path, default=Path("data/required_families.json"))
    args = parser.parse_args()

    banned = {"0UB.89.24931", "0UD.89.24931"}
    opts = load_options(args.options)
    cnstr = load_constraints([args.constraints, args.har_constraints])
    build_cnf(opts, cnstr, banned, args.out_cnf, args.out_varmap, args.out_required)


if __name__ == "__main__":
    main()
