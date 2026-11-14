#!/usr/bin/env python3
"""Stage B: pull monthly NASA products, keep only the pool variables, coarsen to a 5-degree grid.

Two ways to get the data (--mode):
  stream    read only the needed variable straight from the remote file (HTTP range requests). No big download.
            Works for netCDF4/HDF5 files (MERRA-2, GLDAS, FLDAS, GPM, ...). Not for HDF4 (some MODIS/AIRS).
  download  download each granule, reduce it, delete it (disk use = one file per worker)
  auto      (default) try stream; if a granule cannot be streamed, fall back to download for that product.

Probe first (one granule: time, size, grid, sanity stats, estimated total):
    python extract_slice.py variable_pool.csv --product M2TMNXSLV --vars T2M --probe
Real runs (resumable; re-run after any interruption):
    python extract_slice.py variable_pool.csv --product M2TMNXSLV --workers 4
    python extract_slice.py variable_pool.csv --product M2TMNXSLV M2TMNXFLX M2TMNXRAD --workers 4
    python extract_slice.py variable_pool.csv --all --workers 4          # every product in the pool, skipping finished ones

Without --vars, ALL pool variables of the product are extracted in the same pass (almost free once the file is open).

Output per variable: data/raw5/<product>.<variable>.npz with
    data float32 (n_months, 36, 72) (NaN = no data), months int32 YYYYMM, lat (36), lon (72), units, long_name, var_id
Coarsening: each native point goes into its 5x5 degree cell; cell value = cos(lat)-weighted mean of the valid points.
"""
import argparse
import csv
import glob
import os
import re
import shutil
import sys
import tempfile
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

CELL = 5.0
NLAT, NLON = int(180 / CELL), int(360 / CELL)
LAT_C = -90 + CELL / 2 + CELL * np.arange(NLAT)
LON_C = -180 + CELL / 2 + CELL * np.arange(NLON)
LAT_NAMES = ("lat", "latitude", "Latitude", "YDim", "y")
LON_NAMES = ("lon", "longitude", "Longitude", "XDim", "x")
BIG = 1e10


# ------------------------------------------------------------------ grid helpers
def cell_index(lat, lon):
    la = np.clip(np.floor((np.asarray(lat, float) + 90) / CELL).astype(int), 0, NLAT - 1)
    lo = np.floor((((np.asarray(lon, float) + 180) % 360)) / CELL).astype(int) % NLON
    idx = la[:, None] * NLON + lo[None, :]
    w = np.cos(np.deg2rad(np.asarray(lat, float)))[:, None] * np.ones(len(lon))[None, :]
    return idx, np.clip(w, 1e-6, None)


def coarsen(field, idx, w):
    ok = np.isfinite(field)
    v = np.where(ok, field, 0.0)
    ww = np.where(ok, w, 0.0)
    s = np.bincount(idx.ravel(), (v * ww).ravel(), NLAT * NLON)
    d = np.bincount(idx.ravel(), ww.ravel(), NLAT * NLON)
    out = np.full(NLAT * NLON, np.nan, np.float32)
    good = d > 0
    out[good] = (s[good] / d[good]).astype(np.float32)
    return out.reshape(NLAT, NLON)


def finish(arr, dims, latd, lond, lat, lon):
    """arr with named dims -> (nlat, nlon) ascending in latitude, extra dims (time, lev, orbit pass) averaged."""
    if latd not in dims or lond not in dims:
        raise ValueError(f"cannot match lat/lon dims {latd},{lond} to variable dims {dims}")
    extra = tuple(i for i, d in enumerate(dims) if d not in (latd, lond))
    if extra:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            arr = np.nanmean(arr, axis=extra)
        dims = [d for d in dims if d in (latd, lond)]
    if dims.index(latd) > dims.index(lond):
        arr = arr.T
    arr = np.where(np.abs(arr) > BIG, np.nan, arr)
    if lat[0] > lat[-1]:
        lat, arr = lat[::-1], arr[::-1, :]
    return arr, lat, lon


def regular_grid(shape_y, shape_x):
    if abs(shape_y * 2 - shape_x) > 1:
        raise ValueError(f"no lat/lon variables and a {shape_y}x{shape_x} grid is not a 1:2 global grid")
    return 90 - (np.arange(shape_y) + 0.5) * 180.0 / shape_y, -180 + (np.arange(shape_x) + 0.5) * 360.0 / shape_x


def pick_coord(scopes, names):
    for sc in scopes:
        for n in names:
            if n in sc.variables:
                return sc.variables[n]
    return None


# ------------------------------------------------------------------ readers
def read_field(path, hdf_group, name):
    """netCDF4 reader for a local file (also reads HDF4 where the netCDF4 build supports it)."""
    import netCDF4
    with netCDF4.Dataset(path) as ds:
        g = ds
        for part in [p for p in (hdf_group or "").split("/") if p]:
            g = g.groups[part]
        v = g.variables[name]
        dims = list(v.dimensions)
        latv, lonv = pick_coord((g, ds), LAT_NAMES), pick_coord((g, ds), LON_NAMES)
        if latv is not None and lonv is not None:
            lat, lon = np.asarray(latv[:], float), np.asarray(lonv[:], float)
            latd, lond = latv.dimensions[0], lonv.dimensions[0]
        else:
            latd = next((d for d in dims if d.startswith("YDim")), dims[-2])
            lond = next((d for d in dims if d.startswith("XDim")), dims[-1])
            lat, lon = regular_grid(v.shape[dims.index(latd)], v.shape[dims.index(lond)])
        v.set_auto_maskandscale(True)
        arr = v[:]
        arr = np.ma.filled(arr.astype(float), np.nan) if np.ma.isMaskedArray(arr) else np.asarray(arr, float)
        units, long_name = getattr(v, "units", ""), getattr(v, "long_name", "")
    arr, lat, lon = finish(arr, dims, latd, lond, lat, lon)
    return arr, lat, lon, units, long_name


def _attr(attrs, *keys):
    for k in keys:
        if k in attrs:
            x = attrs[k]
            x = np.ravel(x)[0] if np.ndim(x) else x
            return x.decode() if isinstance(x, bytes) else x
    return None


def read_field_h5(fobj, hdf_group, name):
    """h5netcdf reader for a file-like object: reads ONLY the requested variable (range requests when remote)."""
    import h5netcdf
    with h5netcdf.File(fobj, "r") as f:
        g = f
        for part in [p for p in (hdf_group or "").split("/") if p]:
            g = g[part]
        v = g.variables[name]
        dims = list(v.dimensions)
        latv, lonv = pick_coord((g, f), LAT_NAMES), pick_coord((g, f), LON_NAMES)
        if latv is not None and lonv is not None:
            lat, lon = np.asarray(latv[:], float), np.asarray(lonv[:], float)
            latd, lond = latv.dimensions[0], lonv.dimensions[0]
        else:
            latd = next((d for d in dims if d.startswith("YDim")), dims[-2])
            lond = next((d for d in dims if d.startswith("XDim")), dims[-1])
            lat, lon = regular_grid(v.shape[dims.index(latd)], v.shape[dims.index(lond)])
        raw = np.asarray(v[:]).astype(float)
        a = v.attrs
        for key in ("_FillValue", "missing_value"):
            fv = _attr(a, key)
            if fv is not None:
                raw[raw == float(fv)] = np.nan
        lo_, hi_ = _attr(a, "valid_min"), _attr(a, "valid_max")
        vr = a["valid_range"] if "valid_range" in a else None
        if vr is not None:
            lo_, hi_ = float(np.ravel(vr)[0]), float(np.ravel(vr)[1])
        if lo_ is not None:
            raw[raw < float(lo_)] = np.nan
        if hi_ is not None:
            raw[raw > float(hi_)] = np.nan
        sc, off = _attr(a, "scale_factor"), _attr(a, "add_offset")
        raw = raw * (float(sc) if sc is not None else 1.0) + (float(off) if off is not None else 0.0)
        units, long_name = _attr(a, "units") or "", _attr(a, "long_name") or ""
    arr, lat, lon = finish(raw, dims, latd, lond, lat, lon)
    return arr, lat, lon, str(units), str(long_name)


# ------------------------------------------------------------------ metadata helpers
def month_of(result):
    try:
        b = result["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
        return int(b[:4]) * 100 + int(b[5:7])
    except Exception:
        pass
    m = re.search(r"(20\d{2})[-_.]?(\d{2})", str(result.get("meta", {}).get("native-id", "")))
    return int(m.group(1)) * 100 + int(m.group(2)) if m else None


def load_pool(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    prods = {}
    for r in rows:
        prods.setdefault(r["product"], []).append(r)
    return prods


# ------------------------------------------------------------------ one granule
def process_granule(earthaccess, result, rows, mode, state):
    """Returns ({variable: 5deg array}, info dict). May switch state['mode'] from stream to download."""
    t0 = time.time()
    info = {}
    use_stream = mode in ("stream", "auto") and not state.get("no_stream")
    fields = None
    if use_stream:
        try:
            fobj = earthaccess.open([result])[0]
            fields = {}
            try:
                for r in rows:
                    fields[r["variable"]] = read_field_h5(fobj, r["hdf_group"], r["variable"])
            finally:
                try:
                    fobj.close()
                except Exception:
                    pass
            info["how"] = "stream"
        except Exception as e:
            if mode == "stream":
                raise
            if not state.get("no_stream"):
                state["no_stream"] = True
                print(f"  streaming not possible for this product ({type(e).__name__}: {str(e)[:90]}); using download mode")
            fields = None
    if fields is None:
        tmp = tempfile.mkdtemp(prefix="extract_")
        try:
            files = earthaccess.download([result], tmp, show_progress=False)
            if not files:
                raise RuntimeError("download returned no file")
            path = str(files[0])
            info["size_mb"] = os.path.getsize(path) / 1e6
            fields = {r["variable"]: read_field(path, r["hdf_group"], r["variable"]) for r in rows}
            info["how"] = "download"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out, meta = {}, {}
    for name, (arr, lat, lon, units, ln) in fields.items():
        key = (len(lat), len(lon))
        if state.get("grid") != key:
            state["idx"], state["w"] = cell_index(lat, lon)
            state["grid"] = key
        idx, w = state["idx"], state["w"]
        out[name] = coarsen(arr, idx, w)
        meta[name] = (arr, units, ln)
    info["seconds"] = time.time() - t0
    return out, info, meta


_EA = None
_STATE = {}


def _init_worker(ea_obj):
    """Each worker process logs in on its own (credentials were saved by the main process)."""
    global _EA
    if ea_obj is None:
        import earthaccess
        earthaccess.login(strategy="all", persist=True)
        warnings.filterwarnings("ignore", category=FutureWarning)
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        ea_obj = earthaccess
    _EA = ea_obj


def _job(result, rows, mode, cache, m):
    out, info, _ = process_granule(_EA, result, rows, mode, _STATE)
    np.savez_compressed(os.path.join(cache, f"{m}.npz"), **out)
    return m, info


def run_product(earthaccess, product, rows, a, ea_obj=None):
    s_y, s_m = map(int, a.start.split("-"))
    e_y, e_m = map(int, a.end.split("-"))
    outdir = os.path.join(a.out, "raw5")
    done_files = [os.path.join(outdir, f"{product}.{r['variable']}.npz") for r in rows]
    if not a.probe and all(os.path.exists(f) for f in done_files) and not a.force:
        print(f"{product}: already extracted, skipping")
        return True
    t0 = time.time()
    res = earthaccess.search_data(short_name=product, temporal=(f"{a.start}-01", f"{a.end}-28"), count=2000)
    by_month = {}
    for r in res:
        m = month_of(r)
        if m and s_y * 100 + s_m <= m <= e_y * 100 + e_m:
            by_month.setdefault(m, r)
    months = sorted(by_month)
    expect = (e_y - s_y) * 12 + e_m - s_m + 1
    print(f"\n{product} ({len(rows)} variables): {len(res)} granules, {len(months)} months in window "
          f"(expected {expect}) [search {time.time()-t0:.0f}s]")
    if not months:
        print("  no granules found: wrong short name, or no monthly granules")
        return False
    if len(months) != expect:
        miss = [f"{y}{m:02d}" for y in range(s_y, e_y + 1) for m in range(1, 13)
                if s_y * 100 + s_m <= y * 100 + m <= e_y * 100 + e_m and y * 100 + m not in by_month]
        print(f"  WARNING: {len(miss)} months missing, first few: {miss[:8]}")
    if len(res) > len(months) * 1.5:
        print("  WARNING: many more granules than months: may not be a monthly product (daily/5-day?)")

    cache = os.path.join(a.out, "cache", product)
    os.makedirs(cache, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    state = {}

    if a.probe:
        pick = [m for m in months if m == 201506] or [months[len(months) // 2]]
        out, info, meta = process_granule(earthaccess, by_month[pick[0]], rows, a.mode, state)
        wcell = np.cos(np.deg2rad(LAT_C))[:, None] * np.ones(NLON)[None, :]
        for r in rows:
            arr, units, ln = meta[r["variable"]]
            c = out[r["variable"]]
            ok = np.isfinite(c)
            print(f"  {r['variable']}: native {arr.shape}, units '{units}', '{ln}'")
            print(f"     native NaN {100*np.isnan(arr).mean():.1f}% | 5-deg NaN {100*(~ok).mean():.1f}% | "
                  f"native range {np.nanmin(arr):.4g}..{np.nanmax(arr):.4g} | 5-deg area-weighted mean "
                  f"{(c[ok]*wcell[ok]).sum()/wcell[ok].sum():.4g}")
        n = len(months)
        per = info["seconds"]
        print(f"\nPROBE {pick[0]}: mode={info['how']}, {per:.1f}s for this granule"
              + (f", file {info['size_mb']:.0f} MB" if 'size_mb' in info else ""))
        print(f"Estimated {product}, {n} months: ~{per*n/60/a.workers:.0f} min with {a.workers} workers "
              f"(first granule includes login/connection set-up, so this is pessimistic)")
        return True

    need = {r["variable"] for r in rows}

    def cached_ok(m):
        f = os.path.join(cache, f"{m}.npz")
        try:
            return os.path.exists(f) and need <= set(np.load(f).files)
        except Exception:
            return False

    todo = [m for m in months if a.force or not cached_ok(m)]
    print(f"  {len(months)-len(todo)} cached, {len(todo)} to do, mode={a.mode}, workers={a.workers}")
    t1 = time.time()
    n_done = 0
    with ProcessPoolExecutor(max_workers=max(1, a.workers), initializer=_init_worker, initargs=(ea_obj,)) as ex:
        futs = {ex.submit(_job, by_month[m], rows, a.mode, cache, m): m for m in todo}
        for f in as_completed(futs):
            m = futs[f]
            try:
                f.result()
                n_done += 1
                if n_done % 12 == 0 or n_done == len(todo):
                    print(f"  {n_done}/{len(todo)} done ({(time.time()-t1)/60:.1f} min)", flush=True)
            except Exception as e:
                print(f"  {m}: FAILED ({type(e).__name__}: {str(e)[:100]})")
    have = {m for m in months if cached_ok(m)}
    gone = [m for m in months if m not in have]
    if gone:
        print(f"  {len(gone)} months missing (first: {gone[:6]}); re-run the same command to retry")
        return False
    for r in rows:
        data = np.stack([np.load(os.path.join(cache, f"{m}.npz"))[r["variable"]] for m in months]).astype(np.float32)
        fn = os.path.join(outdir, f"{product}.{r['variable']}.npz")
        np.savez_compressed(fn, data=data, months=np.array(months, np.int32), lat=LAT_C, lon=LON_C,
                            units=r["units"], long_name=r["long_name"], var_id=r["var_id"])
        print(f"  wrote {fn}  shape {data.shape}  NaN {100*np.isnan(data).mean():.1f}%")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pool", help="variable_pool.csv")
    ap.add_argument("--product", nargs="+", default=None)
    ap.add_argument("--all", action="store_true", help="every product in the pool")
    ap.add_argument("--vars", nargs="*", default=None, help="only these variables (single product only)")
    ap.add_argument("--start", default="2005-01")
    ap.add_argument("--end", default="2024-12")
    ap.add_argument("--out", default="data")
    ap.add_argument("--mode", choices=["auto", "stream", "download"], default="auto")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--probe", action="store_true", help="one granule only; writes nothing")
    ap.add_argument("--force", action="store_true", help="ignore cache / finished outputs")
    a = ap.parse_args()

    prods = load_pool(a.pool)
    names = list(prods) if a.all else (a.product or [])
    if not names:
        sys.exit("give --product NAME [NAME ...] or --all")
    for n in names:
        if n not in prods:
            sys.exit(f"{n} is not in {a.pool}. Products: {sorted(prods)}")
    if a.vars and len(names) != 1:
        sys.exit("--vars works with exactly one product")
    import earthaccess
    earthaccess.login(strategy="all", persist=True)
    warnings.filterwarnings("ignore", category=FutureWarning)
    ok_all = True
    for n in names:
        rows = prods[n]
        if a.vars:
            bad = [v for v in a.vars if v not in {r["variable"] for r in rows}]
            if bad:
                sys.exit(f"not in pool for {n}: {bad}")
            rows = [r for r in rows if r["variable"] in a.vars]
        try:
            ok_all &= bool(run_product(earthaccess, n, rows, a))
        except Exception as e:
            ok_all = False
            print(f"{n}: FAILED ({type(e).__name__}: {e}); continuing with the next product")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
