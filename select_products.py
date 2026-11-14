#!/usr/bin/env python3
"""Select trend-ready NASA products from the CSVs written by list_collections.py.

Usage:
  python select_products.py collections.csv gaps_ges.csv gaps_modis.csv
  python select_products.py *.csv --top 6          # keep at most 6 per group
  python select_products.py *.csv --min-years 20 --min-end 2024

Steps: classify into groups -> hard filters -> one product per measurement
(Terra/Aqua, daily/monthly and resolution duplicates collapse) -> score -> write CSV.
Default keeps every survivor, because variable selection comes later.
"""
import argparse, csv, re, sys
from datetime import date

NOW = date.today()
NOW_F = NOW.year + (NOW.month - 1) / 12

# ---------- groups (first match wins) ----------
GROUPS = [
    ("Land models & water balance", r"GLDAS|FLDAS|NLDAS|WLDAS|NCALDAS|GRIDMET|water balance|^M2TMNX(LND|GLC|LFO)|^M2SMNX"),
    ("Precipitation",               r"precipitation|^GPCP|^GPM_3IMERG|^TRMM_3B4"),
    ("Vegetation greenness",        r"vegetation ind|ndvi|\bevi\b|leaf area|fpar|vegetation continuous|phenology|^VIP"),
    ("Productivity & water use",    r"evapotranspiration|gross primary|net primary|^MICASA|carbon flux"),
    ("Land surface temperature",    r"land surface temperature"),
    ("Land cover, fire & water",    r"land cover|burned area|thermal anomal|fire|forest cover|water mask|water reservoir|tree cover"),
    ("Radiation & albedo",          r"albedo|brdf|radiation|photosynthetically"),
    ("Aerosols",                    r"aerosol|\baod\b|maiac|^M2TMNXAER|^M2TMNXADG"),
    ("Air-quality gases & ozone",   r"\bno2\b|nitrogen dioxide|\bso2\b|sulfur dioxide|sulphur dioxide|\bn2o\b|hno3|co2|carbon monoxide|methane|ozone|^M2TMNXCHM|^M2IMNXGAS|^M2_TMAX_PM25"),
    ("Atmosphere state",            r"^M2|^AIR|^SNDR|merra-2|airs/aqua"),
]

# ---------- hard exclusions ----------
NOISE_NAME = re.compile(r"^(M2_|gnssro|VJ1|VJ2|VNP|MCD43D|ECO|CAM5K3|AST|OCO|TROPIC|TRPS|S5P|GL(?!DAS)[A-Z]{3,}|GWELD|GFCC|LPJ|MSU|RAIN_|TOMS|ACOS)")
NOISE_TITLE = re.compile(r"near real|\bnrt\b|early precip|late precip|climatolog|long term mean|land/sea|mask(?!.*water)|landslide|"
                         r"uncert|kml|g-lihit|slant|swath|radiance|brightness|echo|reflectivity|latent heating|"
                         r"quality|assimilation.*innov|diurnal|ground validation|hyperspectral|gridded orbital", re.I)
MODEL_RE = re.compile(r"^(M2|GLDAS|FLDAS|NLDAS|WLDAS|NCALDAS|MICASA|GMAO|WaterBalance)|merra-2|land surface model", re.I)
REGIONAL_RE = re.compile(r"conus|north and south america|central asia|alaska|europe|africa only|china|india", re.I)
TERRA = re.compile(r"^MOD|terra", re.I)

# time step overrides when the title does not say it
STEP_OVERRIDE = {"OMNO2d": "daily", "OMSO2e": "daily"}

def timestep(short, title):
    if short in STEP_OVERRIDE:
        return STEP_OVERRIDE[short]
    t = title.lower()
    if re.search(r"monthly|1 month|tavgm|\bmonth\b", t): return "monthly"
    if re.search(r"yearly|annual|multi-year", t):        return "yearly"
    if re.search(r"\b(4|5|7|8|15|16)[- ]?days?\b", t):   return "multiday"
    if re.search(r"daily|1 day|\bstatd\b", t):           return "daily"
    if re.search(r"hourly|half.hourly|1\.5 hours|5-min|3.hourly|\b1 hour\b", t): return "subdaily"
    return "unknown"

STEP_SCORE = {"monthly": 3.0, "yearly": 1.5, "multiday": 1.5, "daily": 1.0, "unknown": 0.5, "subdaily": -9}

def resolution_deg(title):
    t = title.lower()
    m = re.search(r"(\d*\.?\d+)\s*(?:x\s*\d*\.?\d+\s*)?(?:°|deg)", t)
    if m: return float(m.group(1))
    if "cmg" in t: return 0.05
    m = re.search(r"(\d+(?:\.\d+)?)\s*km", t)
    if m: return float(m.group(1)) / 111
    m = re.search(r"(\d+)\s*m\b", t)
    if m: return float(m.group(1)) / 111000
    return None

def classify(short, title):
    s = f"{short} {title}"
    for name, pat in GROUPS:
        if re.search(pat, short, re.I) or re.search(pat, title, re.I):
            return name
    return None

def measurement_key(group, title):
    t = title.lower()
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"modis/|terra\+aqua|terra|aqua|snpp|viirs|noaa-?\d+|suomi.?npp", " ", t)
    t = re.sub(r"monthly|yearly|annual|daily|hourly|1 month|1 day|\d+[- ]?days?|\b3 hourly|tavg\w|stat\w", " ", t)
    t = re.sub(r"[\d.]+\s*(x\s*[\d.]+\s*)?(deg\w*|°|km|m)\b|cmg|sin grid|\bv\d+(\.\d+)?\b|\bl[1-4][a-z]?\b|global|gridded|gap-filled", " ", t)
    t = re.sub(r"[^a-z]+", " ", t).strip()
    return group + "|" + t

def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--min-years", type=float, default=15)
    ap.add_argument("--min-end", type=int, default=2023, help="drop records that ended before this year")
    ap.add_argument("--top", type=int, default=0, help="max products per group (0 = keep all)")
    ap.add_argument("--out", default="selected_products.csv")
    a = ap.parse_args()

    rows = {}
    for f in a.csvs:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            k = r["short_name"]
            if k not in rows or vkey(r["version"]) > vkey(rows[k]["version"]):
                rows[k] = r                       # keep newest version of each product

    stats = {"read": len(rows), "no group": 0, "noise/level": 0, "short or ended": 0}
    cands = []
    for s, r in rows.items():
        title, lvl = r["title"], r["level"]
        g = classify(s, title)
        if g is None: stats["no group"] += 1; continue
        if NOISE_NAME.match(s) and not re.match(r"^(M2TMNX|M2SMNX|M2IMNX)", s): stats["noise/level"] += 1; continue
        if NOISE_TITLE.search(title) or not lvl.strip().startswith(("3", "4")): stats["noise/level"] += 1; continue
        sy = int(r["start"][:4]) + (int(r["start"][5:7]) - 1) / 12
        ongoing = r["end"] == "ongoing"
        ey = NOW_F if ongoing else int(r["end"][:4]) + (int(r["end"][5:7]) - 1) / 12
        years = ey - sy
        if years < a.min_years or (not ongoing and int(r["end"][:4]) < a.min_end): stats["short or ended"] += 1; continue
        step = timestep(s, title)
        if step == "subdaily": stats["noise/level"] += 1; continue
        res = resolution_deg(title)
        regional = bool(REGIONAL_RE.search(title))
        score = STEP_SCORE[step]
        score += min(years, 40) / 40 * 2
        score += 2 if ongoing else 1
        if res is None: score += 0.3
        elif 0.04 <= res <= 1.5: score += 1.0
        elif res > 1.5: score += 0.3
        score -= 1.5 if regional else 0
        score += 0.1 if "cmg" in title.lower() else 0
        score += 0.2 if TERRA.search(s + " " + title) else 0
        cands.append(dict(group=g, short_name=s, version=r["version"], start=r["start"][:4],
                          end="ongoing" if ongoing else r["end"][:4], years=round(years, 1),
                          timestep=step, res_deg=None if res is None else round(res, 3),
                          regional="yes" if regional else "", source="model" if MODEL_RE.search(s + " " + title) else "satellite",
                          score=round(score, 2), title=title, concept_id=r.get("concept_id", ""),
                          _key=measurement_key(g, title)))

    best = {}
    for c in cands:                                # one product per measurement
        if c["_key"] not in best or c["score"] > best[c["_key"]]["score"]:
            best[c["_key"]] = c
    sel = sorted(best.values(), key=lambda c: (c["group"], -c["score"], c["short_name"]))
    if a.top:
        out, n = [], {}
        for c in sel:
            n[c["group"]] = n.get(c["group"], 0) + 1
            if n[c["group"]] <= a.top: out.append(c)
        sel = out

    cols = ["group", "short_name", "version", "start", "end", "years", "timestep", "res_deg",
            "regional", "source", "score", "title", "concept_id"]
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(sel)

    print(f"read {stats['read']} products | dropped: {stats['no group']} no group, "
          f"{stats['noise/level']} noise/level/sub-daily, {stats['short or ended']} short or ended")
    print(f"{len(cands)} passed filters -> {len(sel)} after one-per-measurement\n")
    for g in sorted({c['group'] for c in sel}):
        gs = [c for c in sel if c["group"] == g]
        print(f"{g} ({len(gs)})")
        for c in gs[:4]:
            print(f"   {c['short_name']:<22}{c['start']}-{c['end']:<8}{c['timestep']:<9}{c['source']:<10}{c['score']}")
    print(f"\nwrote {a.out}")

if __name__ == "__main__":
    main()
