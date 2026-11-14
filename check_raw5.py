#!/usr/bin/env python3
"""Sanity-check extracted variables (data/raw5/*.npz) before computing trends.

Flags: wrong shape / empty months, impossible values for the units (temperature outside 150-350 K, fill-value
leftovers, negative values for quantities that cannot be negative), and two variables with identical value ranges
(a sign that names were swapped). Prints one line per variable with the 1st/99th percentile so a human can read it.

Usage: python check_raw5.py [glob]      (default data/raw5/*.npz)
"""
import glob
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
NONNEG_HINT = ("precip", "rain", "snowf", "runoff", "evap", "cloud", "mass", "burden", "aod", "tau", "depth", "speed")


def main():
    files = sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "data/raw5/*.npz"))
    sig, bad = {}, 0
    for f in files:
        vid = os.path.basename(f)[:-4]
        z = np.load(f, allow_pickle=True)
        a = z["data"].astype(float)
        units, name = str(z["units"]), str(z["long_name"]).lower()
        x = a[np.isfinite(a)]
        flags = []
        if x.size == 0:
            print(f"{vid:46s} ALL NaN")
            bad += 1
            continue
        lo, hi = np.percentile(x, [1, 99])
        if a.shape[1:] != (36, 72):
            flags.append(f"grid {a.shape}")
        if a.shape[0] != 240:
            flags.append(f"{a.shape[0]} months")
        if np.isnan(a).all(axis=(1, 2)).any():
            flags.append(f"{int(np.isnan(a).all(axis=(1, 2)).sum())} empty months")
        if units in ("K", "degree_K", "kelvin") and (x.min() < 100 or x.max() > 400):
            flags.append("temperature outside 100-400 K")
        if x.min() < -1e4 or x.max() > 1e12:
            flags.append("fill value leftovers")
        if any(h in name for h in NONNEG_HINT) and (x < -1e-6 * max(abs(hi), 1e-30)).mean() > 0.01:
            flags.append("many negatives for a non-negative quantity")
        key = ("%.5g" % x.min(), "%.5g" % x.max(), "%.5g" % np.mean(x))
        if key in sig:
            flags.append(f"identical stats to {sig[key]}")
        sig[key] = vid
        bad += bool(flags)
        print(f"{vid:46s} {units[:10]:10s} p1 {lo:11.4g} p99 {hi:11.4g}  {'; '.join(flags) if flags else 'ok'}")
    print(f"\n{len(files)} variables, {bad} flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
