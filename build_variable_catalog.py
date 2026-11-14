#!/usr/bin/env python3
"""List the variables of every product in pool_products.csv -> variable_catalog.csv.

For each product it downloads ONE sample granule (a single month, then deletes it),
lists every variable (name, long name, units, dimensions) and classifies it:
    KEEP    plain lat-lon field, looks like a real geophysical quantity
    REVIEW  needs your call (extra dimension such as pressure levels, static field, ...)
    DROP    QC / count / uncertainty / flag / mask / bounds / not a lat-lon field
DROP rows stay in the CSV with a reason, nothing is hidden.

Setup (once):
    pip install earthaccess netCDF4 numpy
    pip install pyhdf        # optional, only for HDF4 files (some MODIS CMG / AIRS); may not install on every OS

Usage:
    python build_variable_catalog.py pool_products.csv
    python build_variable_catalog.py pool_products.csv --only M2TMNXSLV GPM_3IMERGM   # test on a couple first
    python build_variable_catalog.py pool_products.csv --redo MOD11C3                  # redo one product

It is RESUMABLE: products already in the output CSV are skipped, rows are written after
each product, and one failing product never stops the run (it gets an ERROR row).
Expect roughly 30-150 MB per downloaded sample file, one at a time.
"""
import argparse
import csv
import os
import re
import sys
import tempfile

LAT = {"lat", "latitude", "ydim", "nlat", "y"}
LON = {"lon", "longitude", "xdim", "nlon", "x"}
TIME_RE = re.compile(r"time|date|month", re.I)
DATA_EXT = (".nc4", ".nc", ".hdf", ".h5", ".hdf5", ".he5")

# QC / helper variables. Long tokens: substring match. Short tokens: whole-token match.
QC_SUBSTR = ["flag", "count", "nobs", "stdev", "uncertain", "error", "quality", "sigma",
             "weight", "bnds", "bounds", "mask", "numobs", "npix", "nsamp", "validpix", "fillvalue"]
QC_TOKENS = re.compile(r"(?<![a-z])(qc|qa|std|sdev|cnt|num|n)(?![a-z])", re.I)
QC_LONGNAME = re.compile(r"standard deviation|uncertaint|quality|number of|count of|flag|random error|"
                         r"observation count|valid pixel|fraction of valid|mask", re.I)
COORD_NAMES = {"lat", "lon", "time", "lev", "latitude", "longitude", "level", "plev", "nv", "bnds",
               "xdim", "ydim", "crs", "spatial_ref"}


# ---------------------------------------------------------------- reading files
def read_netcdf(path):
    """All variables of a netCDF4 / HDF5 file, walking sub-groups (e.g. IMERG's 'Grid')."""
    import netCDF4
    out = []

    def walk(g, prefix):
        for name, v in g.variables.items():
            dims = list(v.dimensions)
            out.append({
                "group": prefix, "name": name, "dims": dims, "shape": list(v.shape),
                "long_name": str(getattr(v, "long_name", "") or getattr(v, "standard_name", "") or ""),
                "units": str(getattr(v, "units", "") or ""),
                "kind": getattr(v.dtype, "kind", "O"),
                "is_coord": len(dims) == 1 and dims[0] == name,
            })
        for gname, sub in g.groups.items():
            walk(sub, f"{prefix}/{gname}" if prefix else gname)

    with netCDF4.Dataset(path) as ds:
        walk(ds, "")
    return out


def read_hdf4(path):
    from pyhdf.SD import SD, SDC
    sd = SD(path, SDC.READ)
    out = []
    for name, (dnames, shape, _typ, _idx) in sd.datasets().items():
        attrs = sd.select(name).attributes()
        out.append({
            "group": "", "name": name, "dims": [str(d) for d in dnames],
            "shape": list(shape) if hasattr(shape, "__iter__") else [shape],
            "long_name": str(attrs.get("long_name", "")), "units": str(attrs.get("units", "")),
            "kind": "f", "is_coord": False,
        })
    sd.end()
    return out


def read_any(path):
    """Returns (format, variables). Raises with a clear message when unreadable."""
    try:
        return "netcdf/hdf5", read_netcdf(path)
    except Exception as e_nc:
        try:
            return "hdf4", read_hdf4(path)
        except ImportError:
            raise RuntimeError(f"not netCDF/HDF5 ({e_nc}); looks like HDF4 and pyhdf is not installed "
                               f"(pip install pyhdf)")
        except Exception as e_h4:
            raise RuntimeError(f"unreadable: netcdf: {e_nc}; hdf4: {e_h4}")


# ---------------------------------------------------------------- classification
def norm(d):
    return d.split(":")[0].lower()


def classify(v, group_has_time):
    name, long_name = v["name"], v["long_name"]
    low = name.lower()
    if v["kind"] in ("S", "U", "O"):
        return "DROP", "non-numeric"
    if any(s in low for s in QC_SUBSTR) or QC_TOKENS.search(name):
        return "DROP", "QC / count / uncertainty / flag / mask helper variable"
    if QC_LONGNAME.search(long_name):
        return "DROP", f"helper variable by long name ({long_name[:40]})"
    dims = [norm(d) for d in v["dims"]]
    if not (set(dims) & LAT and set(dims) & LON):
        return "DROP", "not a lat-lon field (dims: " + " x ".join(v["dims"]) + ")"
    extra = [(d, s) for d, s in zip(v["dims"], v["shape"])
             if norm(d) not in LAT | LON and not TIME_RE.search(d) and s > 1]
    if extra:
        return "REVIEW", "extra dimension(s): " + ", ".join(f"{d}({s})" for d, s in extra)
    if group_has_time and not any(TIME_RE.search(d) for d in v["dims"]):
        return "REVIEW", "no time dimension although other variables in the file have one (static field?)"
    return "KEEP", ""


def catalog_rows(path, prow):
    fmt, variables = read_any(path)
    data_vars = [v for v in variables if not v["is_coord"] and v["name"].lower() not in COORD_NAMES
                 and not re.search(r"(_bnds|_bounds)$", v["name"], re.I)]
    groups = {}
    for v in data_vars:
        groups.setdefault(v["group"], []).append(v)
    rows = []
    for grp, vs in groups.items():
        group_has_time = any(any(TIME_RE.search(d) for d in v["dims"]) for v in vs)
        for v in vs:
            status, reason = classify(v, group_has_time)
            extra_n = 1
            for d, s in zip(v["dims"], v["shape"]):
                if norm(d) not in LAT | LON and not TIME_RE.search(d) and s > 1:
                    extra_n *= s
            rows.append({
                "product": prow["short_name"], "product_group": prow.get("group", ""),
                "status_product": prow.get("status", ""), "file_format": fmt,
                "hdf_group": grp, "variable": v["name"], "long_name": v["long_name"],
                "units": v["units"], "dims": " x ".join(v["dims"]),
                "shape": "x".join(map(str, v["shape"])),
                "extra_levels": extra_n if extra_n > 1 else "",
                "status": status, "reason": reason,
            })
    return rows


# ---------------------------------------------------------------- download
def fetch_sample(prow, years, tmp):
    import earthaccess
    provider = prow["concept_id"].rsplit("-", 1)[-1] if prow.get("concept_id") else None
    for y in years:
        kwargs = {"short_name": prow["short_name"], "count": 1,
                  "temporal": (f"{y}-06-01", f"{y}-06-30")}
        if prow.get("version"):
            kwargs["version"] = prow["version"]
        if provider:
            kwargs["provider"] = provider
        granules = earthaccess.search_data(**kwargs)
        if granules:
            paths = earthaccess.download(granules, local_path=tmp)
            paths = [str(p) for p in paths if p]
            if not paths:
                continue
            data = [p for p in paths if p.lower().endswith(DATA_EXT)]
            return (data or paths)[0], y
    raise RuntimeError("no granule found for June of " + ", ".join(map(str, years)))


FIELDS = ["product", "product_group", "status_product", "file_format", "hdf_group", "variable",
          "long_name", "units", "dims", "shape", "extra_levels", "status", "reason", "sample_year"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pool", help="pool_products.csv from prune_products.py")
    ap.add_argument("--out", default="variable_catalog.csv")
    ap.add_argument("--year", type=int, default=2015, help="sample year (fallbacks: 2010, 2020)")
    ap.add_argument("--only", nargs="*", default=None, help="only these short names")
    ap.add_argument("--redo", nargs="*", default=[], help="re-run these short names even if done")
    a = ap.parse_args()

    products = list(csv.DictReader(open(a.pool, encoding="utf-8")))
    if a.only:
        products = [p for p in products if p["short_name"] in a.only]

    done = set()
    if os.path.exists(a.out):
        done = {r["product"] for r in csv.DictReader(open(a.out, encoding="utf-8"))} - set(a.redo)
        if a.redo:   # drop old rows of redone products
            old = [r for r in csv.DictReader(open(a.out, encoding="utf-8")) if r["product"] not in a.redo]
            with open(a.out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(old)
    new_file = not os.path.exists(a.out)

    import earthaccess
    earthaccess.login()   # prompts the first time, or uses ~/.netrc / env vars

    ok = err = 0
    with open(a.out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, p in enumerate(products, 1):
            s = p["short_name"]
            if s in done:
                print(f"[{i}/{len(products)}] {s}: already done, skipping")
                continue
            print(f"[{i}/{len(products)}] {s} ...", end=" ", flush=True)
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    path, year = fetch_sample(p, [a.year, 2010, 2020], tmp)
                    rows = catalog_rows(path, p)
                for r in rows:
                    r["sample_year"] = year
                w.writerows(rows)
                n = {k: sum(r["status"] == k for r in rows) for k in ("KEEP", "REVIEW", "DROP")}
                print(f"{len(rows)} variables (KEEP {n['KEEP']}, REVIEW {n['REVIEW']}, DROP {n['DROP']})")
                ok += 1
            except Exception as e:
                msg = str(e).replace("\n", " ")[:300]
                w.writerow({"product": s, "product_group": p.get("group", ""),
                            "status_product": p.get("status", ""), "status": "ERROR", "reason": msg})
                print(f"ERROR: {msg}")
                err += 1
            f.flush()

    print(f"\ndone: {ok} products ok, {err} errors. Catalog: {a.out}")
    if err:
        print("Errors are listed with status=ERROR in the CSV; send them to me.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
