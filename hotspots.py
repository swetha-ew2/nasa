#!/usr/bin/env python3
"""Stage F: variable-specific hotspots ("where is this variable actually changing?").

For each selected variable, on the 5-degree grid:
  1. take the cells with a significant trend (FDR-controlled, from trends.py), split by sign
  2. group neighbouring cells of the same sign into clusters (8-neighbourhood, wrapping over the dateline)
  3. rank clusters by  sum(cos-lat weight x |effect size|)  and keep every cluster of >= 3 cells (at most 10 per sign)
  4. test the cluster's area-mean monthly series with the same statistics as regional.py
Opposite-sign clusters of one variable are listed together: the "same process, opposite trend" case.

IMPORTANT: hotspots are chosen BECAUSE their cells show a significant trend, so the cluster-level p-value is
optimistic (selection bias). They are labelled "exploratory". The honest, fair test remains the cell-level
FDR-controlled map. As an extra check we report whether the cluster trends the same way in both halves of the record.

Outputs data/hotspots/<var_id>.json and data/hotspots/summary.json.   Usage: python hotspots.py [var_id ...]
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage

from regional import region_series, trend_record

MAX_PER_SIGN = 10
MIN_CELLS = 3

# Coarse names for labelling (west, south, east, north). The smallest box containing the cluster centre wins,
# so list specific areas as well as large ones. Labels are for orientation only, not official region borders.
NAMES = [
    ("Amazon Basin", -75, -20, -45, 5), ("Congo Basin", 10, -8, 30, 6), ("Sahel", -18, 10, 40, 18),
    ("Sahara", -18, 18, 35, 32), ("Horn of Africa", 35, -2, 52, 14), ("Southern Africa", 12, -35, 40, -10),
    ("Madagascar & Mozambique Channel", 35, -27, 52, -10), ("Arabian Peninsula", 35, 12, 60, 31),
    ("Middle East", 30, 28, 60, 40), ("Indian Subcontinent", 66, 8, 90, 30), ("Tibetan Plateau", 78, 28, 100, 38),
    ("Southeast Asia", 92, -10, 125, 24), ("Indonesia–Philippines", 95, -11, 141, 8), ("Eastern China", 105, 22, 125, 42),
    ("Mongolia & Inner Asia", 85, 38, 120, 52), ("Siberia", 60, 50, 180, 75), ("Central Asia", 50, 36, 85, 52),
    ("Eastern Europe & Russia", 22, 44, 60, 62), ("Western Europe", -10, 36, 22, 60), ("Scandinavia", 5, 56, 32, 72),
    ("Mediterranean", -6, 30, 36, 45), ("Alaska & Yukon", -170, 55, -130, 72), ("Canadian Arctic", -125, 60, -60, 84),
    ("Western North America", -125, 30, -100, 55), ("Eastern North America", -100, 25, -65, 50),
    ("Central America & Caribbean", -95, 8, -60, 25), ("Northern South America", -80, -5, -50, 12),
    ("Andes", -80, -45, -65, 5), ("Southern South America", -75, -56, -52, -28), ("Australia", 112, -40, 155, -11),
    ("Great Barrier Reef", 142, -25, 155, -10), ("Eastern Australia", 140, -39, 154, -11), ("New Zealand", 165, -48, 180, -34), ("Greenland", -75, 59, -10, 84),
    ("Antarctic Peninsula", -80, -75, -50, -60), ("West Antarctica", -180, -90, -80, -70),
    ("East Antarctica", -80, -90, 180, -65), ("Arctic Ocean", -180, 72, 180, 90),
    ("Southern Ocean", -180, -75, 180, -50), ("North Atlantic", -70, 30, 0, 65), ("Tropical Atlantic", -50, -20, 10, 20),
    ("South Atlantic", -50, -50, 15, -20), ("Gulf of Mexico & Caribbean Sea", -98, 8, -60, 30),
    ("Mediterranean Sea", -6, 30, 36, 45), ("Indian Ocean", 40, -50, 110, 20), ("Bay of Bengal & Arabian Sea", 50, 5, 100, 25),
    ("Western Pacific", 120, -30, 180, 40), ("Tropical Pacific (El Niño region)", -180, -10, -80, 10),
    ("Eastern Pacific", -140, -30, -75, 30), ("North Pacific", 140, 25, 180, 60), ("North Pacific (east)", -180, 25, -120, 60),
    ("South Pacific", -180, -55, -70, -10), ("Africa", -20, -35, 52, 37), ("Asia", 25, 5, 180, 78),
    ("Europe", -10, 35, 40, 72), ("North America", -170, 15, -50, 84), ("South America", -82, -56, -34, 13),
    ("Oceania", 110, -50, 180, 0),
]


OCEAN_NAMES = {"Arctic Ocean", "Southern Ocean", "North Atlantic", "Tropical Atlantic", "South Atlantic",
               "Gulf of Mexico & Caribbean Sea", "Mediterranean Sea", "Great Barrier Reef", "Indian Ocean", "Bay of Bengal & Arabian Sea",
               "Western Pacific", "Tropical Pacific (El Niño region)", "Eastern Pacific", "North Pacific",
               "North Pacific (east)", "South Pacific", "Madagascar & Mozambique Channel"}
_LAND = []


def land_mask():
    """(36, 72) True where the 5-degree cell contains land (cells with MOD11C3 land-surface-temperature data)."""
    if not _LAND:
        d = np.load("data/raw5/MOD11C3.LST_Day_CMG.npz", allow_pickle=True)["data"].astype(float)
        _LAND.append(np.isfinite(d).mean(axis=0) > 0.5)
    return _LAND[0]


def name_cell(lat_c, lon_c, is_land):
    """smallest named box of the right kind (land / ocean) that contains the cell centre"""
    best, best_area = None, 1e18
    for nm, w, s, e, n in NAMES:
        if (nm in OCEAN_NAMES) == is_land:
            continue
        if w <= lon_c <= e and s <= lat_c <= n and (e - w) * (n - s) < best_area:
            best, best_area = nm, (e - w) * (n - s)
    return best


BROAD = {"Africa", "Asia", "Europe", "North America", "South America", "Oceania"}


def compass(lat_c, lon_c, box):
    """'Northern', 'Central-west' ... : where the point sits inside a (w, s, e, n) box, as a 3 x 3 grid"""
    w, s, e, n = box
    fy = (lat_c - s) / max(n - s, 1e-9)
    fx = (lon_c - w) / max(e - w, 1e-9)
    ns = "Northern" if fy > 2 / 3 else "Southern" if fy < 1 / 3 else ""
    ew = "Eastern" if fx > 2 / 3 else "Western" if fx < 1 / 3 else ""
    if ns and ew:
        return f"{ns[:5]}-{ew.lower()}"
    return ns or ew or "Central"


def name_cluster(cell_lat, cell_lon, cell_land, bbox):
    """Plain-language name for a cluster. Broad names (Africa, Asia ...) get a compass word (Western Africa)."""
    from collections import Counter
    c = Counter(name_cell(a, b, l) for a, b, l in zip(cell_lat, cell_lon, cell_land))
    named = [(n, k) for n, k in c.most_common() if n]
    total = len(cell_lat)
    if not named:
        w, s, e, n = bbox
        fl = lambda v, p, q: f"{abs(v):.0f}°{p if v >= 0 else q}"
        return f"{fl(s, 'N', 'S')}–{fl(n, 'N', 'S')}, {fl(w, 'E', 'W')}–{fl(e, 'E', 'W')}"
    top, k = named[0]
    if total >= 40 and k / total < 0.6:
        names = [n for n, _ in named[:3]]
        return ", ".join(names[:-1]) + " & " + names[-1] if len(names) > 1 else names[0]
    if top in BROAD:
        box = next(b for b in NAMES if b[0] == top)[1:]
        cl = float(np.mean(cell_lat))
        co = float(np.mean(cell_lon))
        top = f"{compass(cl, co, box)} {top}"
    return top + (" (wide area)" if total >= 40 else "")


def dedupe(found):
    """two hotspots of one variable must not share a name: add a compass word (west / east / north / south)"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in found:
        groups[r["name"]].append(r)
    for nm, rs in groups.items():
        if len(rs) < 2:
            continue
        lat_span = max(r["centroid"][0] for r in rs) - min(r["centroid"][0] for r in rs)
        lon_span = max(r["centroid"][1] for r in rs) - min(r["centroid"][1] for r in rs)
        if lat_span >= lon_span:
            order, words = sorted(rs, key=lambda r: r["centroid"][0]), ("south", "north")
        else:
            order, words = sorted(rs, key=lambda r: r["centroid"][1]), ("west", "east")
        for i, r in enumerate(order):
            r["name"] = f"{nm} ({words[0] if i == 0 else words[-1] if i == len(order) - 1 else 'central'})"
            if len(order) > 2 and i not in (0, len(order) - 1):
                r["name"] = f"{nm} ({i + 1})"


def clusters(mask):
    """8-connected clusters on the (36, 72) grid with longitude wrap-around -> label array, n."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    parent = list(range(n + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for r in range(mask.shape[0]):                     # join clusters that touch across the 180 degree seam
        for dr in (-1, 0, 1):
            rr = r + dr
            if 0 <= rr < mask.shape[0] and lab[r, -1] and lab[rr, 0]:
                parent[find(lab[r, -1])] = find(lab[rr, 0])
    out = np.zeros_like(lab)
    for i in range(1, n + 1):
        out[lab == i] = find(i)
    ids = [i for i in np.unique(out) if i]
    remap = {old: new for new, old in enumerate(ids, 1)}
    for old, new in remap.items():
        out[out == old] = new
    return out, len(ids)


def lon_extent(cols, lon):
    """west/east of a cluster, handling clusters that cross the dateline."""
    cols = sorted(set(cols))
    if 0 in cols and len(lon) - 1 in cols:             # crosses the seam: find the largest gap
        gaps = [(cols[i + 1] - cols[i], i) for i in range(len(cols) - 1)]
        g, i = max(gaps)
        if g > 1:
            return lon[cols[i + 1]] - 2.5, lon[cols[i]] + 2.5 + 360
    return lon[cols[0]] - 2.5, lon[cols[-1]] + 2.5


def analyse(vid, outdir):
    tr = np.load(f"data/trends/{vid}.npz")
    raw = np.load(f"data/raw5/{vid}.npz", allow_pickle=True)
    data, months, lat, lon = raw["data"].astype(float), raw["months"], tr["lat"], tr["lon"]
    t = (months // 100 - months[0] // 100) + ((months % 100) - 1) / 12.0
    slope, sig, snr = tr["slope"], tr["sig"], tr["snr"]
    cosw = np.cos(np.deg2rad(lat))[:, None] * np.ones(len(lon))[None, :]
    found = []
    for sign, label in ((1, "increasing"), (-1, "decreasing")):
        mask = sig & np.isfinite(slope) & (np.sign(slope) == sign)
        lab, n = clusters(mask)
        cand = []
        for i in range(1, n + 1):
            cells = lab == i
            if cells.sum() < MIN_CELLS:
                continue
            score = float((cosw * np.abs(np.nan_to_num(snr)) * cells).sum())
            cand.append((score, i))
        for score, i in sorted(cand, reverse=True)[:MAX_PER_SIGN]:
            cells = lab == i
            rr, cc = np.nonzero(cells)
            w = cosw * cells
            ser, cover = region_series(data, w)
            if not np.isfinite(ser).mean() > 0.9:
                continue
            west, east = lon_extent(cc.tolist(), lon)
            south, north = lat[rr.min()] - 2.5, lat[rr.max()] + 2.5
            lat_c = float((lat[rr] * cosw[rr, cc]).sum() / cosw[rr, cc].sum())
            lon_c = float(np.degrees(np.arctan2((np.sin(np.radians(lon[cc])) * cosw[rr, cc]).sum(),
                                                (np.cos(np.radians(lon[cc])) * cosw[rr, cc]).sum())))
            rec = dict(
                id=f"{vid}#{label[:3]}{len(found) + 1}", variable=vid, direction=label,
                name=name_cluster(lat[rr], lon[cc], land_mask()[rr, cc], [west, south, east, north]),
                bbox=[round(float(west), 1), round(float(south), 1), round(float(east), 1), round(float(north), 1)],
                centroid=[round(lat_c, 1), round(lon_c, 1)], n_cells=int(cells.sum()),
                area_share=round(float(w.sum() / cosw.sum()), 4),
                cells=[[float(lat[a]), float(lon[b])] for a, b in zip(rr, cc)],
                mean_cell_slope_per_decade=float(f"{np.nanmean(slope[cells]):.4g}"),
                score=float(f"{score:.4g}"), cover=round(cover, 3),
                exploratory=True,
                note="Chosen because its cells are significant, so this cluster-level p-value is optimistic.",
            )
            rec.update(trend_record(ser, months, t))
            # consistency check: same sign of the (OLS-free) Sen slope in the first and second half?
            half = len(t) // 2
            sl = []
            for sl_t, sl_y in ((t[:half], rec["anomaly"][:half]), (t[half:], rec["anomaly"][half:])):
                y = np.array([np.nan if v is None else v for v in sl_y], float)
                ok = np.isfinite(y)
                sl.append(float(np.polyfit(sl_t[ok], y[ok], 1)[0]))
            rec["halves_slope_per_decade"] = [float(f"{x * 10:.4g}") for x in sl]
            rec["consistent_in_both_halves"] = bool(np.sign(sl[0]) == np.sign(sl[1]) == sign)
            found.append(rec)
    found.sort(key=lambda r: -r["score"])
    dedupe(found)
    out = dict(var_id=vid, units=str(raw["units"]), long_name=str(raw["long_name"]),
               n_sig_cells=int(sig.sum()), hotspots=found)
    os.makedirs(outdir, exist_ok=True)
    json.dump(out, open(os.path.join(outdir, vid + ".json"), "w"), separators=(",", ":"))
    return out


def main():
    ids = sys.argv[1:]
    if not ids:
        sel = json.load(open("data/selection/selection.json"))
        ids = sel["headline"] + sel["data_driven"]
    summary = {}
    for vid in ids:
        out = analyse(vid, "data/hotspots")
        summary[vid] = [{k: h[k] for k in ("id", "name", "direction", "n_cells", "slope_per_decade", "ci95", "p",
                                          "consistent_in_both_halves", "centroid")} for h in out["hotspots"]]
        print(f"\n{vid}  [{out['units']}]  {out['n_sig_cells']} significant cells")
        for h in out["hotspots"]:
            print(f"  {h['direction'][:4]}  {h['name'][:34]:34s} {h['n_cells']:3d} cells  "
                  f"{h['slope_per_decade']:+.3g}/dec  p={h['p']:.2g}  halves {'agree' if h['consistent_in_both_halves'] else 'DISAGREE'}")
    json.dump(summary, open("data/hotspots/summary.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
