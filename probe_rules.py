#!/usr/bin/env python3
"""
Probe Porsche configurator feasibility oracle to extract add/remove rules.

This script uses the public feasibility-notification endpoint (unauthenticated)
to test adding individual options on top of a chosen base state. Responses are
decoded with the same pool decoder as parse_har.py and written to data/constraints.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple
from urllib.parse import urlencode

import requests


def decode_pool(pool: List[Any]) -> Any:
    """Same decoder as parse_har.py."""
    sys.setrecursionlimit(max(50000, sys.getrecursionlimit()))
    cache: Dict[int, Any] = {}
    n = len(pool)

    def decode_idx(idx: int) -> Any:
        if isinstance(idx, bool):  # type: ignore[unreachable]
            return idx
        if idx < 0:
            return None if idx in (-7, -5) else idx
        if idx >= n:
            return idx
        if idx in cache:
            return cache[idx]
        cache[idx] = None
        cache[idx] = decode_val(pool[idx])
        return cache[idx]

    def decode_val(val: Any) -> Any:
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return decode_idx(val)
        if isinstance(val, list):
            return [decode_val(v) for v in val]
        if isinstance(val, dict):
            out: Dict[Any, Any] = {}
            for k, v in val.items():
                if isinstance(k, str) and k.startswith("_") and k[1:].isdigit():
                    key_dec = decode_idx(int(k[1:]))
                else:
                    key_dec = k
                out[key_dec] = decode_val(v)
            return out
        return val

    return decode_idx(0)


def load_options(path: Path) -> Dict[str, Dict[str, Any]]:
    import csv

    options: Dict[str, Dict[str, Any]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            options[row["optionId"]] = row
    return options


def load_seeds(path: Path) -> List[List[str]]:
    return [list(s) for s in json.load(path.open())]


def format_options(opts: Iterable[str]) -> str:
    return ".".join(sorted(opts))


def fetch_feasibility(option_added: str, base_options: List[str]) -> Dict[str, Any]:
    params = {
        "optionAdded": option_added,
        "options": format_options(base_options),
        "_routes": "customer-feasibility",
    }
    url = f"https://configurator.porsche.com/zh-CN/mode/model/9921B2/feasibility-notification.data?{urlencode(params)}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    decoded = decode_pool(resp.json())
    data = decoded.get("customer-feasibility", {}).get("data", {})
    cs = data.get("changeSet", {}) or {}
    return {
        "optionAdded": option_added,
        "baseOptions": sorted(base_options),
        "engineAddedOptions": [o["id"] for o in cs.get("engineAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "removedOptions": [o["id"] for o in cs.get("removedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "userAddedOptions": [o["id"] for o in cs.get("userAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")],
        "feasibleOptions": data.get("feasibleOptions") or [],
        "status": data.get("futureConflictDetected"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe configurator feasibility rules.")
    parser.add_argument("--options", type=Path, default=Path("data/options.csv"))
    parser.add_argument("--seeds", type=Path, default=Path("data/seeds.json"))
    parser.add_argument("--out", type=Path, default=Path("data/constraints.json"))
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between requests")
    parser.add_argument("--max", type=int, default=None, help="Max probes (for quick dry runs)")
    args = parser.parse_args()

    options = load_options(args.options)
    seeds = load_seeds(args.seeds)
    if not seeds:
        raise SystemExit("no seeds available")
    base_state = sorted(seeds[-2])  # pick state with 59C + 1NJ

    banned = {"0UB.89.24931", "0UD.89.24931"}
    candidates = [
        oid
        for oid, meta in options.items()
        if meta.get("equipmentType") != "tequipment" and oid not in banned
    ]

    already: Set[Tuple[str, str]] = set()
    results: List[Dict[str, Any]] = []
    if args.out.exists():
        results = json.load(args.out.open())
        for r in results:
            already.add((tuple(r.get("baseOptions", [])), r.get("optionAdded")))

    total = 0
    session = requests.Session()
    for oid in candidates:
        if oid in base_state:
            continue
        key = (tuple(base_state), oid)
        if key in already:
            continue
        try:
            res = fetch_feasibility(oid, base_state)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {oid}: {exc}")
            continue
        results.append(res)
        already.add(key)
        total += 1
        if args.max and total >= args.max:
            break
        time.sleep(args.sleep)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"probes stored: {len(results)} (new {total})")


if __name__ == "__main__":
    main()
