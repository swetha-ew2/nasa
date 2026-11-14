#!/usr/bin/env python3
"""Stage C: trend statistics for one extracted variable (data/raw5/<var_id>.npz -> data/trends/<var_id>.npz + .json).

Per 5-degree cell:
  1. monthly anomalies (calendar-month climatology removed)
  2. Sen slope (per decade) and its 95% CI
  3. Mann-Kendall with AR(1) variance inflation (calibrated by simulation) -> p_mk
  4. OLS slope with t-test                                       -> p_ols, plus Durbin-Watson and Shapiro on residuals
Per variable:
  - test choice: OLS t-test if >= 80% of cells have clean residuals (DW 1.5-2.5 and Shapiro p>0.05), else Mann-Kendall
  - Benjamini-Hochberg FDR (q=0.05) over cells on the chosen p-value -> 'sig' map
  - effect size per cell: snr = total change over the period / SD of detrended anomalies
  - divergence = 1 - |A+ - A-| / (A+ + A-) over significant area (cos-lat weighted): 0 = all one sign, 1 = balanced
  - global-mean trend (area-weighted) with the same tests

Usage:  python trends.py data/raw5/M2TMNXSLV.T2M.npz      (or several files)
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import stats

MIN_VALID = 0.9      # cells with fewer valid months than this fraction are skipped (NaN)
ALPHA = 0.05
CLEAN_FRAC = 0.8


def anomalies(x, months):
    """x (T,...) monthly, months YYYYMM -> climatology removed per calendar month."""
    cal = (np.asarray(months) % 100) - 1
    out = np.array(x, dtype=float, copy=True)
    for m in range(12):
        sel = cal == m
        with np.errstate(all="ignore"):
            out[sel] -= np.nanmean(x[sel], axis=0)
    return out


def sen_slopes(t, y):
    i, j = np.triu_indices(len(t), 1)
    dt = t[j] - t[i]
    return (y[j] - y[i]) / dt, np.sign(y[j] - y[i])


def mk_hamed_rao(t, y):
    """Mann-Kendall with the variance inflated by (1+rho1)/(1-rho1), rho1 = lag-1 autocorrelation of the
    detrended ranks. (Name kept; tested: Hamed-Rao itself rejected 8-18% of null series at nominal 5%,
    this version 3.5-7%.) t,y 1-D (NaN already removed).
    Returns slope (per unit t), ci_lo, ci_hi, z, p."""
    n = len(y)
    sl, sg = sen_slopes(t, y)
    S = sg.sum()
    slope = np.median(sl)
    _, cnt = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(cnt * (cnt - 1) * (2 * cnt + 5))) / 18.0
    d = y - slope * t
    r = stats.rankdata(d)
    r = r - r.mean()
    denom = np.sum(r * r)
    rho = np.sum(r[:-1] * r[1:]) / denom
    corr = max(1.0, (1 + rho) / (1 - rho))     # effective-sample-size inflation for AR(1); never deflates
    var_c = var_s * corr
    z = 0.0 if S == 0 else (S - np.sign(S)) / np.sqrt(var_c)
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    # Sen slope CI (Conover), variance corrected
    cz = stats.norm.ppf(1 - ALPHA / 2)
    N = len(sl)
    srt = np.sort(sl)
    lo = int(np.floor((N - cz * np.sqrt(var_c)) / 2))
    hi = int(np.ceil((N + cz * np.sqrt(var_c)) / 2))
    lo, hi = max(lo, 0), min(hi, N - 1)
    return slope, srt[lo], srt[hi], z, p


def ols(t, y):
    res = stats.linregress(t, y)
    resid = y - (res.intercept + res.slope * t)
    dw = np.sum(np.diff(resid) ** 2) / np.sum(resid ** 2)
    sh = stats.shapiro(resid).pvalue
    return res.slope, res.pvalue, dw, sh


def bh_fdr(p, q=ALPHA):
    """Benjamini-Hochberg on a 1-D array with NaNs; returns boolean array of rejections."""
    ok = np.isfinite(p)
    pv = p[ok]
    m = len(pv)
    order = np.argsort(pv)
    thr = q * (np.arange(1, m + 1) / m)
    passed = pv[order] <= thr
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    rej = np.zeros(m, bool)
    rej[order[:k]] = True
    out = np.zeros(len(p), bool)
    out[ok] = rej
    return out


def series_stats(t, y):
    ok = np.isfinite(y)
    if ok.mean() < MIN_VALID:
        return None
    tt, yy = t[ok], y[ok]
    s, lo, hi, z, p_mk = mk_hamed_rao(tt, yy)
    b, p_ols, dw, sh = ols(tt, yy)
    resid_sd = np.std(yy - (np.median(yy - s * tt) + s * tt), ddof=2)
    return dict(slope=s, lo=lo, hi=hi, p_mk=p_mk, ols=b, p_ols=p_ols, dw=dw, sh=sh, sd=resid_sd,
                span=tt[-1] - tt[0])


def process(path, outdir):
    d = np.load(path, allow_pickle=True)
    data, months, lat, lon = d["data"].astype(float), d["months"], d["lat"], d["lon"]
    T, NY, NX = data.shape
    t = (months // 100 - months[0] // 100) + ((months % 100) - 1) / 12.0       # years
    anom = anomalies(data, months)
    names = ["slope", "ci_lo", "ci_hi", "p_mk", "ols", "p_ols", "dw", "shapiro", "snr"]
    M = {k: np.full((NY, NX), np.nan) for k in names}
    for a in range(NY):
        for b in range(NX):
            r = series_stats(t, anom[:, a, b])
            if r is None:
                continue
            M["slope"][a, b], M["ci_lo"][a, b], M["ci_hi"][a, b] = r["slope"] * 10, r["lo"] * 10, r["hi"] * 10
            M["p_mk"][a, b], M["ols"][a, b], M["p_ols"][a, b] = r["p_mk"], r["ols"] * 10, r["p_ols"]
            M["dw"][a, b], M["shapiro"][a, b] = r["dw"], r["sh"]
            M["snr"][a, b] = r["slope"] * r["span"] / r["sd"] if r["sd"] > 0 else np.nan
    valid = np.isfinite(M["p_mk"])
    clean = valid & (M["dw"] > 1.5) & (M["dw"] < 2.5) & (M["shapiro"] > 0.05)
    clean_frac = clean.sum() / max(valid.sum(), 1)
    test = "ols" if clean_frac >= CLEAN_FRAC else "mk"
    p = (M["p_ols"] if test == "ols" else M["p_mk"]).ravel()
    sig = bh_fdr(p).reshape(NY, NX)
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones(NX)[None, :]
    pos = (w * (sig & (M["slope"] > 0))).sum()
    neg = (w * (sig & (M["slope"] < 0))).sum()
    diverg = 1 - abs(pos - neg) / (pos + neg) if pos + neg > 0 else 0.0
    # global mean
    ww = np.where(np.isfinite(anom), w[None], 0)
    g = np.nansum(np.nan_to_num(anom) * ww, axis=(1, 2)) / ww.sum(axis=(1, 2))
    gs = series_stats(t, g)
    summary = dict(
        var_id=str(d["var_id"]), units=str(d["units"]), n_months=int(T), cells_valid=int(valid.sum()),
        test_used=test, clean_residual_fraction=round(float(clean_frac), 3),
        sig_cells=int(sig.sum()), sig_area_fraction=round(float((w * sig).sum() / (w * valid).sum()), 3),
        sig_positive_area=round(float(pos / (w * valid).sum()), 3), sig_negative_area=round(float(neg / (w * valid).sum()), 3),
        divergence=round(float(diverg), 3),
        global_slope_per_decade=float(gs["slope"] * 10), global_ci=[float(gs["lo"] * 10), float(gs["hi"] * 10)],
        global_p_mk=float(gs["p_mk"]), global_p_ols=float(gs["p_ols"]),
    )
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, os.path.basename(path)[:-4])
    np.savez_compressed(base + ".npz", sig=sig, lat=lat, lon=lon, **M)
    json.dump(summary, open(base + ".json", "w"), indent=1)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="data/trends")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--force", action="store_true", help="redo variables that already have results")
    a = ap.parse_args()
    files = [f for f in a.files
             if a.force or not os.path.exists(os.path.join(a.out, os.path.basename(f)[:-4] + ".json"))]
    print(f"{len(files)} to do, {len(a.files) - len(files)} already finished")
    if a.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(a.workers) as ex:
            results = list(ex.map(process, files, [a.out] * len(files)))
    else:
        results = (process(f, a.out) for f in files)
    for s in results:
        if a.quiet:
            print(f"{s['var_id']}: global {s['global_slope_per_decade']:+.3g} {s['units']}/decade, "
                  f"{100*s['sig_area_fraction']:.0f}% significant area")
            continue
        print(f"{s['var_id']}  [{s['units']}]")
        print(f"  test used: {s['test_used']} (clean-residual cells {100*s['clean_residual_fraction']:.0f}%)")
        print(f"  significant (FDR 5%): {s['sig_cells']} cells = {100*s['sig_area_fraction']:.0f}% of area "
              f"(+{100*s['sig_positive_area']:.0f}% / -{100*s['sig_negative_area']:.0f}%), divergence {s['divergence']}")
        lo, hi = s["global_ci"]
        print(f"  global mean trend: {s['global_slope_per_decade']:+.3f} per decade (95% CI {lo:+.3f}..{hi:+.3f}), "
              f"p_mk={s['global_p_mk']:.2g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
