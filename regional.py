#!/usr/bin/env python3
"""Stage E: regional time series + trend statistics for the selected variables.

Regions = the bounding boxes in src/data/regions.ts (so the analysis and the app stay in sync) plus "global".
Each 5-degree cell is weighted by (its overlap with the box) x cos(latitude); a box smaller than a cell therefore
still gets a value, but it is smoothed over the whole 5-degree cell(s) it touches (stated as a caveat in the output).

Per variable and region:
  - monthly area-weighted mean (raw) and its deseasonalised anomaly (calendar-month climatology removed)
  - Sen slope per decade with 95% CI, Mann-Kendall p (AR(1)-corrected), OLS slope and t-test p,
    Durbin-Watson and Shapiro on the OLS residuals, effect size snr = total change / noise SD
  - test used: OLS t-test when residuals look clean (DW 1.5-2.5, Shapiro p > 0.05), otherwise Mann-Kendall
  - Benjamini-Hochberg FDR (5%) across the 11 boxes of one variable; the global mean is tested alone (p < 0.05)
Outputs data/regional/<var_id>.json and data/regional/summary.json.

Usage: python regional.py            (variables come from data/selection/selection.json; or pass var ids)
"""
import json
import os
import re
import sys

import numpy as np

from trends import ALPHA, anomalies, bh_fdr, series_stats

MIN_COVER = 0.5      # a region needs valid cells covering at least this share of its weight


def load_regions(path="src/data/regions.ts"):
    txt = open(path, encoding="utf-8").read()
    regs = []
    for m in re.finditer(r"id:\s*'([^']+)',\s*name:\s*'([^']+)',.*?bbox:\s*\[([^\]]+)\]", txt, re.S):
        w, s, e, n = [float(x) for x in m.group(3).split(",")]
        regs.append(dict(id=m.group(1), name=m.group(2), bbox=[w, s, e, n]))
    regs.append(dict(id="global", name="Global", bbox=[-180, -90, 180, 90]))
    return regs


def region_weights(bbox, lat, lon):
    """(NY, NX) weights: overlap area fraction of each 5-degree cell with the box, times cos(lat)."""
    w, s, e, n = bbox
    la0, la1 = lat - 2.5, lat + 2.5
    lo0, lo1 = lon - 2.5, lon + 2.5
    olat = np.clip(np.minimum(la1, n) - np.maximum(la0, s), 0, None) / 5.0
    olon = np.clip(np.minimum(lo1, e) - np.maximum(lo0, w), 0, None) / 5.0
    return (olat * np.cos(np.deg2rad(lat)))[:, None] * olon[None, :]


def region_series(data, w):
    """weighted mean over valid cells per month -> (T,), plus the share of the region's weight that was valid."""
    valid = np.isfinite(data)
    ww = valid * w[None]
    tot = ww.sum(axis=(1, 2))
    with np.errstate(all="ignore"):
        ser = np.nansum(np.nan_to_num(data) * ww, axis=(1, 2)) / tot
    cover = float(np.median(tot / w.sum())) if w.sum() > 0 else 0.0
    return ser, cover


def r4(x):
    return None if x is None or not np.isfinite(x) else float(f"{x:.4g}")


def trend_record(ser, months, t):
    """Statistics for ONE monthly series (already a region mean). Shared by regional.py and hotspots.py."""
    anom = anomalies(ser[:, None, None], months)[:, 0, 0]
    st = series_stats(t, anom)
    clean = bool(1.5 < st["dw"] < 2.5 and st["sh"] > 0.05)
    test = "ols" if clean else "mk"
    p = st["p_ols"] if clean else st["p_mk"]
    icpt = float(np.nanmedian(anom - st["slope"] * t))     # Sen trend line for plotting
    return dict(
        status="ok", months=[int(m) for m in months],
        raw=[r4(x) for x in ser], anomaly=[r4(x) for x in anom],
        slope_per_decade=r4(st["slope"] * 10), ci95=[r4(st["lo"] * 10), r4(st["hi"] * 10)],
        p_mk=r4(max(st["p_mk"], 1e-16)), ols_per_decade=r4(st["ols"] * 10), p_ols=r4(max(st["p_ols"], 1e-16)),
        durbin_watson=r4(st["dw"]), shapiro_p=r4(st["sh"]), residuals_clean=clean,
        test_used=test, p=r4(max(p, 1e-16)), snr=r4(st["slope"] * st["span"] / st["sd"] if st["sd"] > 0 else np.nan),
        n_months=int(np.isfinite(anom).sum()), sen_intercept=r4(icpt),
        ci_excludes_zero=bool(st["lo"] > 0 or st["hi"] < 0),
    )


def analyse(path, regions, outdir):
    d = np.load(path, allow_pickle=True)
    data, months, lat, lon = d["data"].astype(float), d["months"], d["lat"], d["lon"]
    vid, units, lname = str(d["var_id"]), str(d["units"]), str(d["long_name"])
    t = (months // 100 - months[0] // 100) + ((months % 100) - 1) / 12.0
    res, pvals = [], []
    for reg in regions:
        w = region_weights(reg["bbox"], lat, lon)
        ser, cover = region_series(data, w)
        name = reg["name"] + (" (area with data only)" if reg["id"] == "global" and cover < 0.9 else "")
        rec = dict(id=reg["id"], name=name, bbox=reg["bbox"], cover=r4(cover))
        need = 0.2 if reg["id"] == "global" else MIN_COVER      # land-only / ocean-only variables: global = area with data
        if cover < need or np.isfinite(ser).mean() < 0.9:
            rec["status"] = "no_data" if cover < 0.05 else "insufficient_coverage"
            res.append(rec)
            pvals.append(np.nan)
            continue
        full = trend_record(ser, months, t)
        rec.update(full)
        p = full["p"]
        res.append(rec)
        pvals.append(p)
    # FDR across the 11 boxes only. The global mean is ONE pre-specified test, so it is judged at p < alpha on its own.
    is_g = np.array([r["id"] == "global" for r in res])
    pv = np.array(pvals, float)
    rej = np.zeros(len(res), bool)
    rej[~is_g] = bh_fdr(pv[~is_g], ALPHA)
    rej[is_g] = np.isfinite(pv[is_g]) & (pv[is_g] < ALPHA)
    for rec, r in zip(res, rej):
        if rec["status"] == "ok":
            rec["significant_fdr"] = bool(r)
            rec["direction"] = ("increasing" if rec["slope_per_decade"] > 0 else "decreasing") if r else "no significant trend"
    out = dict(var_id=vid, units=units, long_name=lname, t0=int(months[0]), t1=int(months[-1]),
               fdr_family="the 11 boxes of this variable (global is a single separate test)", regions=res)
    os.makedirs(outdir, exist_ok=True)
    json.dump(out, open(os.path.join(outdir, vid + ".json"), "w"), separators=(",", ":"))
    return out


def main():
    ids = sys.argv[1:]
    if not ids:
        sel = json.load(open("data/selection/selection.json"))
        ids = sel["headline"] + sel["data_driven"]
    regions = load_regions()
    summary = {}
    for vid in ids:
        out = analyse(os.path.join("data/raw5", vid + ".npz"), regions, "data/regional")
        summary[vid] = [{k: r.get(k) for k in ("id", "status", "slope_per_decade", "ci95", "p", "test_used",
                                              "significant_fdr", "direction", "snr", "cover")} for r in out["regions"]]
        ok = [r for r in out["regions"] if r["status"] == "ok"]
        sig = [r for r in ok if r["significant_fdr"]]
        print(f"{vid:42s} {len(ok)}/{len(out['regions'])} regions analysed, {len(sig)} significant after FDR")
    json.dump(dict(regions=regions and [{k: r[k] for k in ("id", "name", "bbox")} for r in regions], variables=summary),
              open("data/regional/summary.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
