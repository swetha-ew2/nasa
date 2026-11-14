#!/usr/bin/env python3
"""Apply the agreed pruning rules to selected_products.csv.

Decisions this script encodes (agreed 2026-11-14):
  * drop known non-trend / non-global products (KNOWN list below)
  * keep monthly (and yearly) products only; daily, 8-day and unknown steps are dropped
  * drop high-resolution tile-grid products (native grid finer than 0.04 degrees)
  * common window 2005-2024: a product must cover all of it

Usage:
    python prune_products.py selected_products.csv
    python prune_products.py selected_products.csv --out-dir results

Writes:
    pruned_report.csv   every input row + status (KEEP / REVIEW / DROP) + reason + note
    pool_products.csv   KEEP + REVIEW rows (input for build_variable_catalog.py)

REVIEW means "needs your call". Those rows stay in pool_products.csv so the variable
catalog can show what is inside them; nothing heavy is downloaded at that stage.
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter

WIN_START, WIN_END = 2005, 2024
MIN_RES_DEG = 0.04          # finer than this = tile / SIN-grid product -> dropped

KNOWN = [  # (regex on short_name, reason) -> DROP
    (r"^M2TMNP(QDT|TDT|UDT|ODT)$", "MERRA-2 tendency product"),
    (r"^M2TMNXCSP$", "COSP satellite-simulator output (simulated, not a measured variable)"),
    (r"^M2SMNX(EDI|PCT)$", "extreme-index / percentile product relative to a 1991-2020 baseline"),
    (r"^(MCD43C[124]|MCD43GF|MCD19A3D|MCD19A1CMGL)$", "BRDF / reflectance parameter set, not a geophysical trend variable"),
    (r"^MCD12(C1|Q2)$", "categorical land cover / land cover dynamics"),
    (r"^MSVOLSO2L4$", "volcanic SO2 event database, not a gridded time series"),
    (r"_MA$", "anomaly copy of another product"),
    (r"^(NLDAS_|WLDAS_|FLDAS_NOAHMP001_G_CA_D$|WaterBalance_Monthly_Historical_GRIDMET$)",
     "regional product (not global)"),
]

REVIEW = [  # (regex on short_name, reason) -> REVIEW (needs the user's call)
    (r"^M2[IT]MNP", "3D pressure-level product (~42 levels per variable): needs a level choice, or drop"),
    (r"^MOD28C3$", "water-reservoir product: may be a per-reservoir table, not a grid"),
    (r"^ML3MB", "MLS 'assorted grids' (zonal / binned): not a plain lat-lon grid"),
    (r"^AIRS3QPM$", "AIRS 'quantization' support product: unclear whether it holds geophysical fields"),
    (r"^GPM_3GPROF", "single-sensor GPROF precipitation: overlaps IMERG and GPCP"),
]

NOTES = [  # (regex, note) -> KEEP but flagged
    (r"^M2IMNX", "instantaneous version; overlaps a time-averaged M2TMNX product"),
    (r"^M2SMNX", "statistics version; overlaps a time-averaged M2TMNX product"),
]


def first_match(rules, short):
    for pat, text in rules:
        if re.search(pat, short):
            return text
    return None


def grid_weight(res):
    if res is None:
        return "unknown"
    if res < 0.25:
        return "heavy"     # fine native grid: coarsen on read
    if res < 1.0:
        return "medium"
    return "light"


def classify(row):
    short = row["short_name"]
    step = row["timestep"]
    try:
        res = float(row["res_deg"]) if row["res_deg"] not in ("", None) else None
    except ValueError:
        res = None

    why = first_match(KNOWN, short)
    if why:
        return "DROP", why
    if step not in ("monthly", "yearly"):
        return "DROP", f"time step is '{step}' (decision: monthly/yearly only)"
    if res is not None and res < MIN_RES_DEG:
        return "DROP", f"high-resolution tile/SIN-grid product ({res} deg; decision: drop for now)"
    try:
        start = int(row["start"][:4])
    except ValueError:
        start = 0
    end = row["end"]
    end_year = 9999 if end == "ongoing" else int(end[:4])
    if start > WIN_START or end_year < WIN_END:
        return "DROP", f"does not cover {WIN_START}-{WIN_END} ({row['start']}..{end})"
    why = first_match(REVIEW, short)
    if why:
        return "REVIEW", why
    return "KEEP", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="selected_products.csv (output of select_products.py)")
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    os.makedirs(a.out_dir, exist_ok=True)
    out = []
    for r in rows:
        status, reason = classify(r)
        note = first_match(NOTES, r["short_name"]) or ""
        res = float(r["res_deg"]) if r["res_deg"] else None
        out.append({**r, "status": status, "reason": reason, "note": note,
                    "grid_weight": grid_weight(res)})

    cols = ["status", "reason", "note", "grid_weight"] + list(rows[0].keys())
    with open(os.path.join(a.out_dir, "pruned_report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    pool = [o for o in out if o["status"] in ("KEEP", "REVIEW")]
    with open(os.path.join(a.out_dir, "pool_products.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(pool)

    c = Counter(o["status"] for o in out)
    print(f"{len(out)} products read: KEEP {c['KEEP']}, REVIEW {c['REVIEW']}, DROP {c['DROP']}\n")
    print("DROP reasons:")
    for reason, n in Counter(o["reason"].split(" (")[0] for o in out if o["status"] == "DROP").most_common():
        print(f"  {n:3d}  {reason}")
    print("\nREVIEW (needs your call):")
    for o in out:
        if o["status"] == "REVIEW":
            print(f"  {o['short_name']:<26} {o['reason']}")
    print("\nKEEP by group:")
    for g in sorted({o["group"] for o in out if o["status"] == "KEEP"}):
        names = [o["short_name"] for o in out if o["status"] == "KEEP" and o["group"] == g]
        print(f"  {g} ({len(names)}): {', '.join(names)}")
    print(f"\nwrote {os.path.join(a.out_dir, 'pruned_report.csv')} and {os.path.join(a.out_dir, 'pool_products.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
