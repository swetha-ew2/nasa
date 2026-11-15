#!/usr/bin/env python3
"""Stage E2: trend statistics for the 58 IPCC AR6 reference regions (land + ocean), on the same 5-degree tiles.

A tile belongs to the region that contains its CENTRE, so every tile is counted at most once and the tile data are
untouched. Regions with too few tiles carrying data are reported as 'too few tiles' instead of being tested.
Benjamini-Hochberg FDR is applied across the IPCC regions of one variable, separately from the 11 hand-picked
regions (regional.py), so the verdicts of those 11 do not change.

Outputs data/regional_ipcc/<var_id>.json, data/ipcc_regions.geojson (simplified outlines) and data/ipcc_tiles.json.
Needs: pip install regionmask
"""
import json
import os
import sys

import numpy as np
import regionmask

from regional import region_series, trend_record, r4
from trends import ALPHA, bh_fdr

MIN_TILES = 3        # tiles with data needed to test a region
MIN_COVER = 0.5      # share of the region's tiles (by weight) that must have data


def build():
    ar6 = regionmask.defined_regions.ar6.all
    regs = []
    for i, num in enumerate(ar6.numbers):
        reg = ar6[num]
        regs.append(dict(num=int(num), id="ar6:" + reg.abbrev, abbrev=reg.abbrev, name=pretty(reg.name),
                         kind="ocean" if int(num) >= 46 else "land", poly=reg.polygon))
    return ar6, regs



PRETTY = {"N.W.": "North-West ", "N.E.": "North-East ", "S.W.": "South-West ", "S.E.": "South-East ", "W.C.": "West-Central ",
          "E.C.": "East-Central ", "N.": "Northern ", "S.": "Southern ", "W.": "Western ", "E.": "Eastern ", "C.": "Central ",
          "Equatorial.": "Equatorial "}
FIX = {"West&Central-Europe": "Western & Central Europe", "S.South-America": "Southern South America",
       "N.Central-America": "Northern Central America", "S.Central-America": "Southern Central America",
       "Greenland/Iceland": "Greenland & Iceland", "N.Australia": "Northern Australia", "C.Australia": "Central Australia",
       "E.Australia": "Eastern Australia", "S.Australia": "Southern Australia", "E.Antarctica": "East Antarctica",
       "W.Antarctica": "West Antarctica", "W.Siberia": "Western Siberia", "E.Siberia": "Eastern Siberia",
       "E.Europe": "Eastern Europe", "N.Europe": "Northern Europe", "E.Asia": "East Asia", "S.Asia": "South Asia",
       "S.E.Asia": "South-East Asia", "W.C.Asia": "West-Central Asia", "E.C.Asia": "East-Central Asia",
       "N.South-America": "Northern South America", "N.Eastern-Africa": "North-Eastern Africa",
       "S.Eastern-Africa": "South-Eastern Africa"}


def pretty(name):
    if name in FIX:
        return FIX[name]
    name = name.replace("-", " ")
    for k, v in PRETTY.items():
        if name.startswith(k):
            name = v + name[len(k):]
            break
    return name.replace("Indic", "Indian")


def tile_members(ar6, lat, lon):
    """(NY, NX) region number of each tile centre, -1 if none"""
    m = ar6.mask(lon, lat)          # NaN where outside every region
    return np.where(np.isfinite(m.values), m.values, -1).astype(int)


def main():
    ids = sys.argv[1:]
    if not ids:
        sel = json.load(open("data/selection/selection.json"))
        ids = sel["headline"] + sel["data_driven"]
    ar6, regs = build()
    d0 = np.load(os.path.join("data/raw5", ids[0] + ".npz"), allow_pickle=True)
    lat, lon = d0["lat"], d0["lon"]
    mem = tile_members(ar6, lat, lon)
    wlat = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))
    os.makedirs("data/regional_ipcc", exist_ok=True)

    # outlines (simplified) + tile membership for the app
    feats = []
    for r in regs:
        poly = r["poly"].simplify(0.4)
        gj = json.loads(json.dumps(poly.__geo_interface__))
        n = int((mem == r["num"]).sum())
        w, s, e, nn = poly.bounds
        big = max(poly.geoms, key=lambda g: g.area) if hasattr(poly, "geoms") else poly     # label sits inside the largest part
        pt = big.representative_point()
        feats.append(dict(type="Feature", properties=dict(id=r["id"], abbrev=r["abbrev"], name=r["name"], kind=r["kind"],
                                                          n_tiles=n, center=[round(pt.x, 2), round(pt.y, 2)]), geometry=gj))
        r["n_tiles"], r["bbox"] = n, [round(w, 1), round(s, 1), round(e, 1), round(nn, 1)]
    json.dump(dict(type="FeatureCollection", features=feats), open("data/ipcc_regions.geojson", "w"), separators=(",", ":"))
    tiles = {f"{lat[i]:g},{lon[j]:g}": regs_by_num(regs, mem[i, j]) for i in range(lat.size) for j in range(lon.size) if mem[i, j] >= 0}
    json.dump(tiles, open("data/ipcc_tiles.json", "w"), separators=(",", ":"))

    for vid in ids:
        d = np.load(os.path.join("data/raw5", vid + ".npz"), allow_pickle=True)
        data, months = d["data"].astype(float), d["months"]
        t = (months // 100 - months[0] // 100) + ((months % 100) - 1) / 12.0
        res, pv = [], []
        for r in regs:
            w = wlat * (mem == r["num"])
            ser, cover = region_series(data, w)
            nvalid = int((np.isfinite(data).mean(axis=0) > 0.9)[mem == r["num"]].sum())
            rec = dict(id=r["id"], name=r["name"], bbox=r["bbox"], cover=r4(cover), n_tiles=r["n_tiles"], n_tiles_data=nvalid,
                       kind=r["kind"])
            if r["n_tiles"] < MIN_TILES or nvalid < MIN_TILES or cover < MIN_COVER or np.isfinite(ser).mean() < 0.9:
                rec["status"] = "no_data" if nvalid == 0 else "insufficient_coverage"
                res.append(rec); pv.append(np.nan)
                continue
            rec.update(trend_record(ser, months, t))
            res.append(rec); pv.append(rec["p"])
        pv = np.array(pv, float)
        rej = np.zeros(len(res), bool)
        ok = np.isfinite(pv)
        rej[ok] = bh_fdr(pv[ok], ALPHA)
        for rec, rj in zip(res, rej):
            if rec["status"] == "ok":
                rec["significant_fdr"] = bool(rj)
                rec["direction"] = ("increasing" if rec["slope_per_decade"] > 0 else "decreasing") if rj else "no significant trend"
        json.dump(dict(var_id=vid, fdr_family="the IPCC regions of this variable that have enough tiles", regions=res),
                  open(f"data/regional_ipcc/{vid}.json", "w"), separators=(",", ":"))
        n_ok = sum(r["status"] == "ok" for r in res)
        print(f"{vid:42s} {n_ok}/{len(res)} IPCC regions tested, {int(rej.sum())} significant after FDR")


def regs_by_num(regs, num):
    return next(r["id"] for r in regs if r["num"] == num)


if __name__ == "__main__":
    sys.exit(main())
