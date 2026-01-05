#!/usr/bin/env python3
"""
Run convergence experiments for multiple base state sizes.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import urlencode

import requests

from converge_probe import BAN, build_base_states, load_options, load_required, load_seeds
from parse_har import decode_pool  # reuse decoder


def load_candidates(options: List[Dict[str, str]]) -> List[str]:
    return [
        o["optionId"]
        for o in options
        if o.get("equipmentType") != "tequipment"
        and o["optionId"] not in BAN
        and o.get("isStandardEquipment") != "True"
    ]


def stable_state(options: List[str]) -> List[str]:
    return sorted(options)


def probe(base: List[str], option: str, session: requests.Session, sleep_sec: float = 0.2) -> Dict[str, Any] | None:
    params = {
        "optionAdded": option,
        "options": ".".join(sorted(base)),
        "_routes": "customer-feasibility",
    }
    url = f"https://configurator.porsche.com/zh-CN/mode/model/9921B2/feasibility-notification.data?{urlencode(params)}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:  # noqa: BLE001
        print(f"[warn] request failed for {option} on state ({len(base)} opts): {exc}")
        return None
    decoded = decode_pool(resp.json())
    data = decoded.get("customer-feasibility", {}).get("data", {})
    cs = data.get("changeSet", {}) or {}
    result = {
        "baseOptions": sorted(base),
        "optionAdded": option,
        "engineAddedOptions": [o["id"] for o in cs.get("engineAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "removedOptions": [o["id"] for o in cs.get("removedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "userAddedOptions": [o["id"] for o in cs.get("userAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "feasibleOptions": data.get("feasibleOptions") or [],
    }
    time.sleep(sleep_sec)
    return result


def gather_constraints(base_states: List[List[str]], candidates: List[str], cache: Dict[Tuple[str, str], Dict[str, Any]], sleep_sec: float) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    session = requests.Session()
    for base in base_states:
        base_key = ".".join(sorted(base))
        for opt in candidates:
            key = (base_key, opt)
            if key in cache:
                results.append(cache[key])
                continue
            res = probe(base, opt, session=session, sleep_sec=sleep_sec)
            if res is None:
                continue
            cache[key] = res
            results.append(res)
    return results


def write_constraints(path: Path, constraints: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(constraints, f, ensure_ascii=False, indent=2)


def calc_stats(constraints: List[Dict[str, Any]], base_states_count: int) -> Dict[str, Any]:
    added_rules: Set[Tuple[str, str]] = set()
    removed_rules: Set[Tuple[str, str]] = set()
    for r in constraints:
        oa = r.get("optionAdded")
        for a in r.get("engineAddedOptions", []) or []:
            added_rules.add((oa, a))
        for rm in r.get("removedOptions", []) or []:
            removed_rules.add((oa, rm))
    return {
        "base_states_count": base_states_count,
        "probed_pairs_count": len(constraints),
        "unique_rule_count": len(added_rules) + len(removed_rules),
    }


def run_build_cnf(run_dir: Path, har_constraints: Path) -> Tuple[int, int]:
    from build_cnf import build_cnf

    options = load_options(Path("data/options.csv"))
    constraints = []
    constraints.extend(json.load((run_dir / "constraints.json").open()))
    if har_constraints.exists():
        constraints.extend(json.load(har_constraints.open()))
    banned = BAN

    out_cnf = run_dir / "model.cnf"
    out_varmap = run_dir / "varmap.json"
    out_required = run_dir / "required_families.json"
    required = load_required(Path("data/required_families.json"))

    build_cnf(options, constraints, banned, out_cnf, out_varmap, out_required)

    # read back clause/var counts
    vars_count = 0
    clauses_count = 0
    with out_cnf.open() as f:
        for line in f:
            line = line.strip()
            if line.startswith("p"):
                parts = line.split()
                vars_count = int(parts[2])
                clauses_count = int(parts[3])
                break
    return vars_count, clauses_count


def run_count(run_dir: Path) -> int:
    from count import load_cnf, count_models

    cnf_path = run_dir / "model.cnf"
    num_vars, clauses = load_cnf(cnf_path)
    count = count_models(num_vars, clauses)
    (run_dir / "count_result.txt").write_text(str(count), encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Run convergence experiments.")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 10, 30, 100])
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--out-dir", type=Path, default=Path("runs"))
    args = parser.parse_args()

    options = load_options(Path("data/options.csv"))
    required = load_required(Path("data/required_families.json"))
    seeds = load_seeds(Path("data/seeds.json"))
    candidates = load_candidates(options)

    cache_file = args.out_dir / "probe_cache.json"
    cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if cache_file.exists():
        raw = json.load(cache_file.open())
        for k, v in raw.items():
            cache[tuple(k.split("|"))] = v

    convergence_rows = []
    prev_rules: Set[Tuple[str, str, str]] = set()
    prev_count: int | None = None

    for n in args.sizes:
        run_dir = args.out_dir / f"N{n}"
        run_dir.mkdir(parents=True, exist_ok=True)
        base_states = build_base_states(options, required, seeds, n, k=args.k)
        (run_dir / "base_states.json").write_text(json.dumps(base_states, ensure_ascii=False, indent=2), encoding="utf-8")

        constraints = gather_constraints(base_states, candidates, cache, sleep_sec=args.sleep)
        write_constraints(run_dir / "constraints.json", constraints)

        stats = calc_stats(constraints, len(base_states))
        vars_count, clauses_count = run_build_cnf(run_dir, Path("data/feasibility_from_har.json"))
        cnt = run_count(run_dir)

        # update cache on disk
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_str = {f"{k[0]}|{k[1]}": v for k, v in cache.items()}
        cache_file.write_text(json.dumps(cache_str, ensure_ascii=False, indent=2), encoding="utf-8")

        # compute deltas
        current_rules: Set[Tuple[str, str, str]] = set()
        for r in constraints:
            oa = r.get("optionAdded")
            for a in r.get("engineAddedOptions", []) or []:
                current_rules.add(("add", oa, a))
            for rm in r.get("removedOptions", []) or []:
                current_rules.add(("rem", oa, rm))
        new_rules = len(current_rules - prev_rules)
        ratio = cnt / prev_count if prev_count else None
        delta_log10 = None
        if prev_count:
            import math

            delta_log10 = math.log10(cnt) - math.log10(prev_count)
        row = {
            "N": n,
            "probed_pairs": stats["probed_pairs_count"],
            "unique_rules": stats["unique_rule_count"],
            "cnf_vars": vars_count,
            "cnf_clauses": clauses_count,
            "count": str(cnt),
            "log10_count": float(__import__("math").log10(cnt)),
            "ratio_to_prev": ratio,
            "delta_log10": delta_log10,
            "new_rules_vs_prev": new_rules,
        }
        convergence_rows.append(row)
        prev_rules = current_rules
        prev_count = cnt

        (run_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[N={n}] pairs={stats['probed_pairs_count']} rules={stats['unique_rule_count']} count={cnt}")

    # write convergence tables
    table_md = ["|N|probed|(rules)|vars|clauses|count|log10|ratio_to_prev|delta_log10|new_rules_vs_prev|", "|-|-|-|-|-|-|-|-|-|-|"]
    for r in convergence_rows:
        table_md.append(
            f"|{r['N']}|{r['probed_pairs']}|{r['unique_rules']}|{r['cnf_vars']}|{r['cnf_clauses']}|{r['count']}|{r['log10_count']:.2f}|"
            f"{'' if r['ratio_to_prev'] is None else f'{r['ratio_to_prev']:.4g}'}|"
            f"{'' if r['delta_log10'] is None else f'{r['delta_log10']:.4f}'}|{r['new_rules_vs_prev']}|"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "convergence_table.md").write_text("\n".join(table_md), encoding="utf-8")

    import csv as _csv

    with (args.out_dir / "convergence_table.csv").open("w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(
            f,
            fieldnames=[
                "N",
                "probed_pairs",
                "unique_rules",
                "cnf_vars",
                "cnf_clauses",
                "count",
                "log10_count",
                "ratio_to_prev",
                "delta_log10",
                "new_rules_vs_prev",
            ],
        )
        writer.writeheader()
        for r in convergence_rows:
            writer.writerow(r)


if __name__ == "__main__":
    main()
