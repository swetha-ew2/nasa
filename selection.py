#!/usr/bin/env python3
"""Stage D: data-driven variable selection (unsupervised, "Option A").

Idea: each variable has a map of trend effect sizes (snr, from trends.py). Pick the smallest set of variables whose
maps jointly reconstruct the trend structure of the WHOLE candidate pool (orthogonal matching pursuit on the maps).

Steps
 1. Screen   : keep variables with FDR-significant area >= --min-sig-area and valid data on >= --min-valid of cells.
 2. Normalise: snr map, cos-lat weighted, missing cells = 0, scaled to a unit vector.
 3. Forward  : greedily add the variable that most reduces the unexplained energy of the pool.
 4. Elbow    : stop when the next variable adds < --elbow of explained energy (min 3, max --max-k).
 5. Ablation : drop-one and drop-whole-family loss of explained energy.
 6. Stability: block bootstrap (20-degree blocks of cells); a variable is "re-found" if the replicate picks it
               or a near-duplicate (|r| >= --dup).
 7. Report   : redundancy (who is covered by whom) and divergence flags (opposing regional trends).

Usage: python selection.py            (reads data/trends/*.npz|json, variable_pool.csv for families)
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np

# Headline variables: always shown, chosen by hand because students look for them first (plain data, edit freely).
# The data-driven selection is then computed on top of them, so it adds what the headlines do NOT already cover.
HEADLINE = [
    "M2TMNXSLV.T2M",                          # near-surface air temperature
    "REYNOLDS_NCDC_L4_MONTHLY_V5.sst",        # sea surface temperature
    "NASA_SSH_REF_SIMPLE_GRID_V11.ssha",      # sea level
    "GPM_3IMERGM.precipitation",              # precipitation (regional wet/dry divergence)
    "MOD10CM.Snow_Cover_Monthly_CMG",         # snow cover
    "MOD13C2.CMG 0.05 Deg Monthly NDVI",      # vegetation greenness
]


def load_pool(trend_dir, args):
    fam = {}
    if os.path.exists(args.pool):
        for r in csv.DictReader(open(args.pool)):
            fam[r["var_id"]] = r.get("family", "")
    ids, maps, meta, dropped = [], [], {}, []
    lat = None
    for jf in sorted(glob.glob(os.path.join(trend_dir, "*.json"))):
        s = json.load(open(jf))
        vid = s["var_id"]
        z = np.load(jf[:-5] + ".npz")
        lat = z["lat"]
        snr = z["snr"]
        valid_frac = np.isfinite(snr).mean()
        if not np.isfinite(snr).any() or np.nanmax(np.abs(snr)) == 0:
            dropped.append((vid, "empty or constant in the source data"))
            continue
        if s["sig_area_fraction"] < args.min_sig_area:
            dropped.append((vid, f"significant area {100*s['sig_area_fraction']:.1f}% < {100*args.min_sig_area:.0f}%"))
            continue
        if valid_frac < args.min_valid:
            dropped.append((vid, f"valid cells {100*valid_frac:.0f}% < {100*args.min_valid:.0f}%"))
            continue
        ids.append(vid)
        maps.append(snr)
        meta[vid] = dict(family=fam.get(vid, "?"), units=s["units"], sig_area=s["sig_area_fraction"],
                         divergence=s["divergence"], global_slope=s["global_slope_per_decade"],
                         global_p=s["global_p_mk"] if s["test_used"] == "mk" else s["global_p_ols"])
    return ids, np.array(maps), lat, meta, dropped


def build_matrix(maps, lat, row_weight=None):
    """maps (V, NY, NX) -> X (cells, V) with unit-norm columns, weighted by sqrt(cos-lat [* bootstrap count])."""
    V, NY, NX = maps.shape
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones(NX)[None, :]
    if row_weight is not None:
        w = w * row_weight
    X = np.nan_to_num(maps, nan=0.0).reshape(V, -1).T * np.sqrt(w.reshape(-1))[:, None]
    n = np.linalg.norm(X, axis=0)
    n[n == 0] = 1.0
    return X / n


def explained(X, S):
    if not S:
        return 0.0
    Q, _ = np.linalg.qr(X[:, S])
    return float(np.sum((Q.T @ X) ** 2) / X.shape[1])


def forward(X, max_k, elbow, min_k=3, start=()):
    """Orthogonal matching pursuit. `start` = columns forced in first (headlines); max_k / elbow apply to the
    variables ADDED after them. Returns (added columns, explained after each addition, explained by `start` alone)."""
    R = X.copy()
    total = X.shape[1]
    for j in start:
        r = R[:, j]
        nr = np.linalg.norm(r)
        if nr > 1e-12:
            q = r / nr
            R = R - np.outer(q, q @ R)
    base = 1 - np.sum(R * R) / total
    S, curve = [], []
    while len(S) < min(max_k, X.shape[1] - len(start)):
        cn = np.sum(R * R, axis=0)
        cn[cn < 1e-12] = np.inf
        g = np.sum((R.T @ R) ** 2, axis=0) / cn        # gain of adding column j = ||R^T r_j||^2 / ||r_j||^2
        g[S] = -1
        g[list(start)] = -1
        j = int(np.argmax(g))
        if g[j] <= 1e-9:
            break
        q = R[:, j] / np.linalg.norm(R[:, j])
        R = R - np.outer(q, q @ R)
        S.append(j)
        curve.append(1 - np.sum(R * R) / total)
        prev = curve[-2] if len(curve) > 1 else base
        if elbow > 0 and len(S) >= min_k and curve[-1] - prev < elbow:
            S.pop()
            curve.pop()
            break
    return S, curve, base


def curve_full(X, max_k, start=()):
    """Explained curve ignoring the elbow, for plotting."""
    return forward(X, max_k, elbow=0.0, start=start)[1]


def bootstrap(maps, lat, ids, forced, chosen_ids, args, rng):
    """Block bootstrap of the data-driven picks (headlines are forced, so they are not tested)."""
    V, NY, NX = maps.shape
    blk = (np.arange(NY)[:, None] // 4) * 100 + (np.arange(NX)[None, :] // 4)      # 20 deg blocks at 5 deg cells
    labels = np.unique(blk)
    X0 = build_matrix(maps, lat)
    C = np.abs(X0.T @ X0)
    found = {v: 0 for v in chosen_ids}
    for _ in range(args.boot):
        pick = rng.choice(labels, size=len(labels), replace=True)
        wmap = np.zeros((NY, NX))
        for b in labels:
            wmap[blk == b] = (pick == b).sum()
        X = build_matrix(maps, lat, wmap)
        S, _, _ = forward(X, args.k, 0.0, start=forced)
        for v in chosen_ids:
            i = ids.index(v)
            if any(C[i, j] >= args.dup for j in S):
                found[v] += 1
    return {v: found[v] / args.boot for v in chosen_ids}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trends", default="data/trends")
    ap.add_argument("--pool", default="variable_pool.csv")
    ap.add_argument("--out", default="data/selection")
    ap.add_argument("--k", type=int, default=14, help="number of data-driven variables added after the headlines")
    ap.add_argument("--headline", nargs="*", default=HEADLINE, help="variables always included")
    ap.add_argument("--min-sig-area", type=float, default=0.0, help="screening on significant area (0 = off)")
    ap.add_argument("--min-valid", type=float, default=0.30, help="screening on data coverage (fraction of cells)")
    ap.add_argument("--boot", type=int, default=20)
    ap.add_argument("--dup", type=float, default=0.9)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ids, maps, lat, meta, dropped = load_pool(args.trends, args)
    if len(ids) < 3:
        print("fewer than 3 variables survive screening; run trends.py first")
        return 1
    missing = [h for h in args.headline if h not in ids]
    if missing:
        print("WARNING: headline variables not available (not extracted, empty, or too little coverage):", missing)
    forced = [ids.index(h) for h in args.headline if h in ids]
    X = build_matrix(maps, lat)
    S, curve, base_h = forward(X, args.k, 0.0, start=forced)
    final = forced + S
    chosen = [ids[i] for i in S]
    full_curve = curve_full(X, min(40, len(ids) - len(forced)), start=forced)
    total = explained(X, final)

    drop_one = {ids[i]: total - explained(X, [j for j in final if j != i]) for i in final}
    fams = sorted({meta[ids[i]]["family"] for i in final})
    drop_fam = {f: total - explained(X, [i for i in final if meta[ids[i]]["family"] != f]) for f in fams}

    rng = np.random.default_rng(args.seed)
    stab = bootstrap(maps, lat, ids, forced, chosen, args, rng) if args.boot > 0 else {}

    C = X.T @ X
    redundancy = {ids[i]: [ids[j] for j in np.argsort(-np.abs(C[i])) if j != i and abs(C[i, j]) >= args.dup]
                  for i in final}
    covered_by = {}
    for j, v in enumerate(ids):
        if j not in final:
            k = max(final, key=lambda s: abs(C[s, j]))
            covered_by[v] = (ids[k], float(C[k, j]))

    os.makedirs(args.out, exist_ok=True)
    roles = {ids[i]: "headline" for i in forced}
    roles.update({v: "data-driven" for v in chosen})
    json.dump(dict(args=vars(args), n_candidates=len(ids), headline=[ids[i] for i in forced], data_driven=chosen,
                   roles=roles, explained_total=total, explained_by_headlines=base_h, curve_after_headlines=curve,
                   drop_one=drop_one, drop_family=drop_fam, stability=stab, redundancy=redundancy,
                   covered_by=covered_by, screened_out=dropped, missing_headlines=missing,
                   meta={v: meta[v] for v in ids}),
              open(os.path.join(args.out, "selection.json"), "w"), indent=1)
    with open(os.path.join(args.out, "selection_curve.csv"), "w") as f:
        f.write("k_added_after_headlines,explained\n")
        for k, e in enumerate(full_curve, 1):
            f.write(f"{k},{e:.4f}\n")

    L = ["# Variable selection report", "",
         f"Candidates: {len(ids)} (left out: {len(dropped)}). Final set: **{len(final)}** variables "
         f"({len(forced)} headline + {len(chosen)} data-driven) explaining **{100*total:.1f}%** of the pool's trend structure "
         f"(headlines alone: {100*base_h:.1f}%).", ""]
    if missing:
        L += [f"**Headline variables not available:** {', '.join(missing)}", ""]
    L += ["## Final set", "", "| # | variable | role | family | +explained | drop-one loss | re-found | global trend/decade | divergence |",
          "|---|---|---|---|---|---|---|---|---|"]
    rows = [(i, "headline", None) for i in forced] + [(i, "data-driven", c) for i, c in zip(S, curve)]
    prev = base_h
    for n, (i, role, c) in enumerate(rows, 1):
        v = ids[i]
        gain = f"{100*(c-prev):.1f}%" if c is not None else "-"
        if c is not None:
            prev = c
        L.append(f"| {n} | {v} | {role} | {meta[v]['family']} | {gain} | {100*drop_one[v]:.1f}% | "
                 f"{('%.0f%%' % (100*stab[v])) if v in stab else '-'} | {meta[v]['global_slope']:+.3g} {meta[v]['units']} | "
                 f"{meta[v]['divergence']:.2f} |")
    L += ["", "## Loss if a whole family is removed", ""] + [f"- {f}: {100*x:.1f}%" for f, x in sorted(drop_fam.items(), key=lambda t: -t[1])]
    L += ["", "## Redundancy (near-duplicates of each shown variable, |r| >= %.2f)" % args.dup, ""]
    for v, r in redundancy.items():
        L.append(f"- **{v}**: " + (", ".join(r) if r else "none"))
    L += ["", "## Strongest regional divergence among candidates (opposing significant trends)", ""]
    for v in sorted(ids, key=lambda v: -meta[v]["divergence"])[:10]:
        L.append(f"- {v}: divergence {meta[v]['divergence']:.2f}" + (f" ({roles[v]})" if v in roles else ""))
    L += ["", "## Left out", ""] + [f"- {v}: {why}" for v, why in dropped]
    open(os.path.join(args.out, "selection_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:6 + len(final) + 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
