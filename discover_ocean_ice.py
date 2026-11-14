#!/usr/bin/env python3
"""Find candidate OCEAN + CRYOSPHERE collections in CMR (public search, no login).

Themes (agreed): sea surface temperature, sea level, sea ice, snow cover.
It searches ALL providers (POCLOUD, NSIDC_*, OB_CLOUD, ...) and prints the best
candidates per theme. It does NOT pick for you: look at the list, then tell me which
one per theme to use.

Usage:
    python discover_ocean_ice.py
    python discover_ocean_ice.py --out ocean_ice_candidates.csv
    python discover_ocean_ice.py --theme "ocean_color=chlorophyll,ocean color"   # add a theme
    python discover_ocean_ice.py --provider POCLOUD --provider NSIDC_CPRD        # restrict

Needs: pip install requests
"""
import argparse
import csv
import re
import sys

import requests

CMR_URL = "https://cmr.earthdata.nasa.gov/search/collections.json"
WIN_START, WIN_END = 2005, 2024

THEMES = {
    "sea_surface_temperature": ["sea surface temperature"],
    "sea_level": ["sea surface height", "sea level anomaly"],
    "sea_ice": ["sea ice concentration", "sea ice extent"],
    "snow_cover": ["snow cover monthly", "snow cover extent"],
}

NOISE_TITLE = re.compile(r"near real|\bnrt\b|swath|\bl2\b|level 2|uncert|forecast|simulat|"
                         r"validation|in situ|buoy|argo float|profile|ship", re.I)


def search(keyword, providers, max_pages=3):
    for page in range(1, max_pages + 1):
        params = {"keyword": keyword, "page_size": 200, "page_num": page}
        if providers:
            params["provider"] = providers          # requests repeats list params
        r = requests.get(CMR_URL, params=params, timeout=60)
        r.raise_for_status()
        entries = r.json().get("feed", {}).get("entry", [])
        yield from entries
        if len(entries) < 200:
            return


def timestep(title):
    t = title.lower()
    if re.search(r"monthly|1 month|\bmonth\b", t):
        return "monthly"
    if re.search(r"yearly|annual", t):
        return "yearly"
    if re.search(r"\b(5|7|8|10)[- ]?days?\b|5day|weekly", t):
        return "multiday"
    if re.search(r"daily|1 day", t):
        return "daily"
    return "unknown"


def resolution_deg(title):
    t = title.lower()
    m = re.search(r"(\d*\.?\d+)\s*(?:x\s*\d*\.?\d+\s*)?(?:°|deg)", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*km", t)
    if m:
        return round(float(m.group(1)) / 111, 3)
    return None


def concerns(theme, short, title, step):
    out = []
    if step == "unknown":
        out.append("time step not in title: monthly granules may exist, check")
    if step in ("daily", "multiday"):
        out.append("needs aggregation to monthly (many files)")
    if theme == "sea_ice" or re.search(r"polar stereographic|ease-?grid", title, re.I) or short.upper().startswith("NSIDC-"):
        out.append("probably a polar grid: needs reprojection to lat-lon, poles only")
    if re.search(r"regional|arctic|antarctic|baltic|mediterranean", title, re.I) and theme != "sea_ice":
        out.append("may be regional")
    return "; ".join(out)


def parse(entry, theme, kw):
    title = entry.get("title") or entry.get("dataset_id") or ""
    short = entry.get("short_name", "")
    start = (entry.get("time_start") or "")[:4]
    end_raw = entry.get("time_end") or ""
    end = end_raw[:4] if end_raw else "ongoing"
    step = timestep(title)
    res = resolution_deg(title)
    return {
        "theme": theme,
        "provider": entry["id"].rsplit("-", 1)[-1],
        "short_name": short,
        "version": entry.get("version_id", ""),
        "start": start,
        "end": end,
        "timestep": step,
        "res_deg": "" if res is None else res,
        "level": entry.get("processing_level_id", ""),
        "concerns": concerns(theme, short, title, step),
        "title": title,
        "concept_id": entry["id"],
        "matched_keyword": kw,
    }


def keep(row):
    if NOISE_TITLE.search(row["title"]):
        return False
    lvl = row["level"].strip().upper().lstrip("L")
    if lvl and not lvl.startswith(("3", "4")):
        return False
    try:
        if int(row["start"]) > WIN_START:
            return False
    except ValueError:
        return False
    if row["end"] != "ongoing" and int(row["end"]) < WIN_END:
        return False
    return True


def score(row):
    s = {"monthly": 3, "unknown": 1.5, "multiday": 1, "yearly": 1, "daily": 0.5}[row["timestep"]]
    s += 2 if row["end"] == "ongoing" else 1
    s += min(2024 - int(row["start"]), 30) / 30 * 2
    s -= 0.5 * bool(row["concerns"])
    return round(s, 2)


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", action="append", default=[], help="restrict to a CMR provider (repeatable)")
    ap.add_argument("--theme", action="append", default=[], help='extra theme: "name=kw1,kw2"')
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--out", default="ocean_ice_candidates.csv")
    a = ap.parse_args()

    themes = dict(THEMES)
    for t in a.theme:
        name, kws = t.split("=", 1)
        themes[name.strip()] = [k.strip() for k in kws.split(",")]

    rows = {}
    for theme, kws in themes.items():
        for kw in kws:
            for e in search(kw, a.provider):
                r = parse(e, theme, kw)
                if not keep(r):
                    continue
                key = (theme, r["short_name"])
                if key not in rows or vkey(r["version"]) > vkey(rows[key]["version"]):
                    rows[key] = r
    ordered = sorted(rows.values(), key=lambda r: (r["theme"], -score(r), r["short_name"]))
    for r in ordered:
        r["score"] = score(r)

    cols = ["theme", "provider", "short_name", "version", "start", "end", "timestep", "res_deg",
            "level", "score", "concerns", "title", "concept_id", "matched_keyword"]
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(ordered)

    print(f"{len(ordered)} candidates written to {a.out} (window filter: covers {WIN_START}-{WIN_END}, level 3/4)\n")
    for theme in themes:
        sub = [r for r in ordered if r["theme"] == theme][: a.top]
        print(f"== {theme} ({len([r for r in ordered if r['theme'] == theme])} found, top {len(sub)})")
        for r in sub:
            print(f"  {r['provider']:<11}{r['short_name']:<34}{r['start']}-{r['end']:<8}{r['timestep']:<9}{r['title'][:60]}")
            if r["concerns"]:
                print(f"{'':13}! {r['concerns']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
