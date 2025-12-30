#!/usr/bin/env python3
"""
Parse Porsche configurator HAR, decode pooled JSON, and export option catalog plus seed states.

Outputs:
- data/options.csv: flattened option metadata for manual inspection.
- data/seeds.json: list of option code sets observed in the HAR (customer-configurator + feasibility).
- data/feasibility_from_har.json: simplified feasibility change sets from HAR responses.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs


def decode_pool(pool: List[Any]) -> Any:
    """
    Decode pooled JSON of the form [{"_1": 2}, "customer-configurator", ...].
    Positive integers are treated as indices into the pool; keys named "_123"
    are resolved to pool[123] and used as dict keys. -7/-5 act as null sentinels.
    Booleans must be handled before ints because bool is a subclass of int.
    """
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
        cache[idx] = None  # placeholder for cyclic refs
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


def load_har(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_har_entries(har: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    return har.get("log", {}).get("entries", [])


def parse_option_codes(raw: str) -> List[str]:
    if not raw:
        return []
    # codes are dot-separated, e.g., "1H.59C.AX"
    return [code for code in raw.split(".") if code]


def collect_customer_configurator(har: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Set[Tuple[str, ...]]]:
    options_by_id: Dict[str, Dict[str, Any]] = {}
    seeds: Set[Tuple[str, ...]] = set()

    for entry in iter_har_entries(har):
        url = entry.get("request", {}).get("url", "")
        content = entry.get("response", {}).get("content", {})
        if ".data" not in url or "customer-configurator" not in url or "text" not in content:
            continue
        decoded = decode_pool(json.loads(content["text"]))
        data = decoded.get("customer-configurator", {}).get("data", {})

        # harvest option catalog from the optionsList view
        for section in data.get("views", {}).get("optionsList", []):
            section_id = section.get("id")
            section_title = section.get("title")
            for category in section.get("categories", []) or []:
                cat_id = category.get("id")
                cat_title = category.get("title")
                for group in category.get("groups", []) or []:
                    group_id = group.get("id")
                    group_title = group.get("title")
                    for item in group.get("items", []) or []:
                        oid = item.get("id")
                        if not oid:
                            continue
                        meta = options_by_id.setdefault(oid, {})
                        meta.update(
                            {
                                "optionId": oid,
                                "title": item.get("title"),
                                "optionType": item.get("optionType"),
                                "family": item.get("family"),
                                "sectionId": section_id,
                                "sectionTitle": section_title,
                                "categoryId": cat_id,
                                "categoryTitle": cat_title,
                                "groupId": group_id,
                                "groupTitle": group_title,
                                "priceNumeric": item.get("priceNumeric"),
                                "isStandardEquipment": bool(item.get("isStandardEquipment")),
                                "isSelected": bool(item.get("isSelected")),
                                "equipmentType": item.get("equipmentType"),
                            }
                        )

        # seed states from configuration options
        config_opts = data.get("configuration", {}).get("options", [])
        if isinstance(config_opts, list) and config_opts:
            seeds.add(tuple(sorted(str(o) for o in config_opts)))

    return options_by_id, seeds


def collect_feasibility(har: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Set[Tuple[str, ...]]]:
    records: List[Dict[str, Any]] = []
    seeds: Set[Tuple[str, ...]] = set()
    for entry in iter_har_entries(har):
        url = entry.get("request", {}).get("url", "")
        content = entry.get("response", {}).get("content", {})
        if ".data" not in url or "feasibility" not in url or "text" not in content:
            continue
        parsed_url = urlparse(url)
        qs = parse_qs(parsed_url.query)
        option_added = qs.get("optionAdded", [None])[0]
        base_options = parse_option_codes(qs.get("options", [""])[0])

        decoded = decode_pool(json.loads(content["text"]))
        data = decoded.get("customer-feasibility", {}).get("data", {})
        change_set = data.get("changeSet", {}) or {}

        engine_added = [o["id"] for o in change_set.get("engineAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")]
        user_added = [o["id"] for o in change_set.get("userAddedOptions", []) or [] if isinstance(o, dict) and o.get("id")]
        removed = [o["id"] for o in change_set.get("removedOptions", []) or [] if isinstance(o, dict) and o.get("id")]
        feasible = data.get("feasibleOptions") or []

        records.append(
            {
                "url": url,
                "optionAdded": option_added,
                "baseOptions": base_options,
                "engineAddedOptions": engine_added,
                "userAddedOptions": user_added,
                "removedOptions": removed,
                "feasibleOptions": feasible,
            }
        )
        if feasible:
            seeds.add(tuple(sorted(str(o) for o in feasible)))
    return records, seeds


def write_options_csv(path: Path, options: Dict[str, Dict[str, Any]]) -> None:
    fieldnames = [
        "optionId",
        "title",
        "optionType",
        "family",
        "sectionId",
        "sectionTitle",
        "categoryId",
        "categoryTitle",
        "groupId",
        "groupTitle",
        "priceNumeric",
        "isStandardEquipment",
        "isSelected",
        "equipmentType",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for oid in sorted(options):
            writer.writerow({k: options[oid].get(k) for k in fieldnames})


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Porsche configurator HAR and export option catalog.")
    parser.add_argument("har", type=Path, help="Path to configurator.porsche.com.har")
    parser.add_argument("--out-dir", type=Path, default=Path("data"), help="Output directory")
    args = parser.parse_args()

    har = load_har(args.har)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    options, cc_seeds = collect_customer_configurator(har)
    feasibility_records, feas_seeds = collect_feasibility(har)

    write_options_csv(args.out_dir / "options.csv", options)
    write_json(args.out_dir / "feasibility_from_har.json", feasibility_records)

    seeds = sorted({tuple(sorted(s)) for s in cc_seeds | feas_seeds})
    write_json(args.out_dir / "seeds.json", seeds)

    print(f"exported {len(options)} options")
    print(f"seed states: {len(seeds)} (customer-configurator {len(cc_seeds)}, feasibility {len(feas_seeds)})")
    if feasibility_records:
        print(f"feasibility records: {len(feasibility_records)}")


if __name__ == "__main__":
    main()
