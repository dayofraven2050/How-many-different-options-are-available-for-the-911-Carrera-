#!/usr/bin/env python3
"""
Generate representative base states for probing using required families and seeds.

Outputs base_states JSON under runs/N{N}/base_states.json.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple


BAN = {"0UB.89.24931", "0UD.89.24931"}


def load_options(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_required(path: Path) -> List[str]:
    return json.load(path.open())


def load_seeds(path: Path) -> List[List[str]]:
    return [list(s) for s in json.load(path.open())]


def family_members(options: List[Dict[str, str]], fam: str) -> List[str]:
    members = [
        o["optionId"]
        for o in options
        if (o.get("family") or "<none>") == fam
        and o.get("equipmentType") != "tequipment"
        and o["optionId"] not in BAN
    ]
    return sorted(members)


def pick_representatives(options: List[Dict[str, str]], fam: str, k: int = 3) -> List[str]:
    members = family_members(options, fam)
    if not members:
        return []
    # sort by (isSelected, isStandardEquipment, optionId)
    def score(oid: str) -> Tuple[int, int, str]:
        meta = next(o for o in options if o["optionId"] == oid)
        sel = 1 if meta.get("isSelected") == "True" else 0
        std = 1 if meta.get("isStandardEquipment") == "True" else 0
        return (sel, std, oid)

    members_sorted = sorted(members, key=score, reverse=True)
    rep = members_sorted[:k]
    # ensure defaults include first element for stability
    return rep


def base_default_state(options: List[Dict[str, str]], seeds: List[List[str]], required: List[str]) -> Set[str]:
    # prefer the longest seed as baseline
    seed = max(seeds, key=len) if seeds else []
    state = set(seed)
    # fill missing families with first representative
    for fam in required:
        members = family_members(options, fam)
        if not members:
            continue
        if not state.intersection(members):
            state.add(members[0])
    return state


def replace_family(state: Set[str], fam_members: List[str], chosen: str) -> Set[str]:
    new_state = set(x for x in state if x not in fam_members)
    new_state.add(chosen)
    return new_state


def generate_pairwise_states(
    options: List[Dict[str, str]],
    required: List[str],
    reps: Dict[str, List[str]],
    default_state: Set[str],
    target: int,
) -> List[Set[str]]:
    states: List[Set[str]] = []
    fams = [f for f in required if reps.get(f)]
    for fa, fb in itertools.combinations(fams, 2):
        for ra in reps[fa]:
            for rb in reps[fb]:
                if len(states) >= target:
                    return states
                sa = replace_family(default_state, family_members(options, fa), ra)
                sab = replace_family(sa, family_members(options, fb), rb)
                states.append(sab)
    return states


def generate_single_states(
    options: List[Dict[str, str]],
    required: List[str],
    reps: Dict[str, List[str]],
    default_state: Set[str],
    target: int,
    existing: List[Set[str]],
) -> List[Set[str]]:
    states: List[Set[str]] = []
    for fam in required:
        for r in reps.get(fam, []):
            if len(existing) + len(states) >= target:
                return states
            states.append(replace_family(default_state, family_members(options, fam), r))
    return states


def dedup(states: List[Set[str]]) -> List[List[str]]:
    seen: Set[Tuple[str, ...]] = set()
    out: List[List[str]] = []
    for st in states:
        key = tuple(sorted(st))
        if key in seen:
            continue
        seen.add(key)
        out.append(list(key))
    return out


def build_base_states(options: List[Dict[str, str]], required: List[str], seeds: List[List[str]], n: int, k: int = 3) -> List[List[str]]:
    reps = {fam: pick_representatives(options, fam, k) for fam in required}
    default = base_default_state(options, seeds, required)

    states: List[Set[str]] = [set(s) for s in seeds]
    states.append(set(default))

    # pairwise coverage
    states.extend(generate_pairwise_states(options, required, reps, default, target=max(0, n - len(states))))
    # single-family variations if still short
    states.extend(generate_single_states(options, required, reps, default, target=n, existing=states))

    # if still short, cycle through families deterministically
    idx = 0
    fams = [f for f in required if reps.get(f)]
    while len(states) < n and fams:
        fam = fams[idx % len(fams)]
        rep_list = reps.get(fam, [])
        if rep_list:
            r = rep_list[(idx // len(fams)) % len(rep_list)]
            states.append(replace_family(default, family_members(options, fam), r))
        idx += 1

    return dedup(states)[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate base states for probing.")
    parser.add_argument("--options", type=Path, default=Path("data/options.csv"))
    parser.add_argument("--required", type=Path, default=Path("data/required_families.json"))
    parser.add_argument("--seeds", type=Path, default=Path("data/seeds.json"))
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("runs"))
    parser.add_argument("--k", type=int, default=3, help="Representatives per family")
    args = parser.parse_args()

    options = load_options(args.options)
    required = load_required(args.required)
    seeds = load_seeds(args.seeds)

    base_states = build_base_states(options, required, seeds, args.n, k=args.k)

    out_dir = args.out_dir / f"N{args.n}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "base_states.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(base_states, f, ensure_ascii=False, indent=2)
    print(f"generated {len(base_states)} base states -> {out_path}")


if __name__ == "__main__":
    main()
