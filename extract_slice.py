#!/usr/bin/env python3
"""Stage B: pull monthly NASA products, keep only the pool variables, coarsen to a 5-degree grid.

How the data is fetched (--mode):
  auto      (default) OPeNDAP first: the server sends ONLY the variable you need (~0.8 MB instead of a 54 MB file).
            Any variable OPeNDAP cannot deliver is read from a downloaded file instead (that file is deleted afterwards).
  opendap   OPeNDAP only (errors instead of falling back)
  download  always download the whole granule, reduce it, delete it
  stream    read from the remote file with h5netcdf (did not work for GES DISC; kept for other servers)
--stride N  OPeNDAP only: take every Nth native point. 0 (default) = automatic: ~0.25 degree spacing, so
            0.5-degree grids are read in full and 0.05-degree MODIS grids every 5th point (400 points per 5-degree cell).

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
import struct
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


# ------------------------------------------------------------------ OPeNDAP (DAP2) reader
DAP_TYPES = {"Float32": (">f4", 4), "Float64": (">f8", 8), "Int16": (">i4", 4), "UInt16": (">u4", 4),
             "Int32": (">i4", 4), "UInt32": (">u4", 4), "Byte": ("u1", 1)}
_DAP_CACHE = {}
_DAP_TEXT = {}
_DAP_COORD = {}


def parse_dds(text, var):
    m = re.search(r"(Float32|Float64|Int16|UInt16|Int32|UInt32|Byte)\s+" + re.escape(var) + r"((?:\[[^\]]+\])+);", text)
    if not m:
        return None
    dims = re.findall(r"\[(\w+)\s*=\s*(\d+)\]", m.group(2))
    return m.group(1), [d for d, _ in dims], [int(n) for _, n in dims]


def parse_das(text, var):
    """attributes of one variable from DAS text -> dict (numbers as float, strings as str)."""
    m = re.search(r"(?:^|\n)\s*" + re.escape(var) + r"\s*\{(.*?)\n\s*\}", text, re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        mm = re.match(r"\s*(\w+)\s+(\w+)\s+(.*?);\s*$", line)
        if not mm:
            continue
        typ, key, val = mm.groups()
        if typ == "String":
            out[key] = val.strip().strip('"')
        else:
            try:
                out[key] = [float(v) for v in val.split(",")]
            except ValueError:
                pass
    return out


def parse_dods(blob, dtype, count):
    i = blob.find(b"\nData:\n")
    if i < 0:
        raise ValueError("no Data marker; response starts " + repr(blob[:150]))
    p = i + len(b"\nData:\n")
    n1, n2 = struct.unpack(">II", blob[p:p + 8])
    if n1 != n2 or n1 != count:
        raise ValueError(f"unexpected element count {n1} (wanted {count})")
    p += 8
    need = n1 * np.dtype(dtype).itemsize
    if len(blob) - p < need:
        raise ValueError(f"response too short: {len(blob)-p} bytes for {n1} values of {dtype}")
    return np.frombuffer(blob[p:p + need], dtype=dtype)


def opendap_url(result):
    for u in result["umm"].get("RelatedUrls", []):
        link = u.get("URL", "")
        if "opendap" in link.lower() or "OPENDAP" in str(u.get("Subtype", "")).upper():
            for suf in (".html", ".dds", ".das", ".dods"):
                if link.endswith(suf):
                    link = link[: -len(suf)]
            return link
    for d in result.data_links():
        if "/data/" in d:
            return d.replace("/data/", "/opendap/")
    raise KeyError("no OPeNDAP address in the granule metadata")


def _get(session, url, what):
    r = session.get(url, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"{what}: HTTP {r.status_code} {r.content[:100]!r}")
    return r


def _ckey(url):
    return url.rsplit("/granules/", 1)[0] if "/granules/" in url else url.rsplit("/", 2)[0]


def dap_meta(session, url, var, stride_req):
    ck = _ckey(url)
    key = (ck, var, stride_req)
    if key in _DAP_CACHE:
        return _DAP_CACHE[key]
    if (ck, "dds") not in _DAP_TEXT:           # one description per collection, not per variable
        _DAP_TEXT[(ck, "dds")] = _get(session, url + ".dds", "dds").text
        _DAP_TEXT[(ck, "das")] = _get(session, url + ".das", "das").text
    dds, das = _DAP_TEXT[(ck, "dds")], _DAP_TEXT[(ck, "das")]
    parsed = parse_dds(dds, var)
    if not parsed:
        raise KeyError(f"variable {var!r} not in the OPeNDAP DDS")
    typ, dims, sizes = parsed
    attrs = parse_das(das, var)
    roles = {}
    for d in dims:
        dl = d.lower()
        if dl.startswith("ydim") or dl.startswith("lat") or d in LAT_NAMES:
            roles[d] = "lat"
        elif dl.startswith("xdim") or dl.startswith("lon") or d in LON_NAMES:
            roles[d] = "lon"
    latd = next((d for d in dims if roles.get(d) == "lat"), None)
    lond = next((d for d in dims if roles.get(d) == "lon"), None)
    if latd is None or lond is None:
        latd, lond = dims[-2], dims[-1]
    ny, nx = sizes[dims.index(latd)], sizes[dims.index(lond)]

    def coord(name, n):
        ckk = (ck, name, n)
        if ckk not in _DAP_COORD:
            c = None
            mt = re.search(r"(Float32|Float64)\s+" + re.escape(name) + r"\[", dds)
            if mt:
                c = parse_dods(_get(session, f"{url}.dods?{name}[0:{n-1}]", name).content, DAP_TYPES[mt.group(1)][0], n).astype(float)
                if len(c) != n:
                    raise ValueError(f"coordinate {name}: got {len(c)} values, expected {n}")
            _DAP_COORD[ckk] = c
        return _DAP_COORD[ckk]
    lat, lon = coord(latd, ny), coord(lond, nx)
    if lat is None or lon is None:
        lat, lon = regular_grid(ny, nx)
    res = abs(lat[1] - lat[0]) if len(lat) > 1 else 1.0
    stride = stride_req if stride_req > 0 else max(1, int(round(0.25 / res)))
    for d, n in zip(dims, sizes):
        if d not in (latd, lond) and n > 8:
            raise ValueError(f"extra dimension {d}={n} (levels?) is not supported")
    shape, ce = [], ""
    for d, n in zip(dims, sizes):
        if d in (latd, lond):
            ce += f"[0:{stride}:{n-1}]"
            shape.append(len(range(0, n, stride)))
        else:
            ce += f"[0:{n-1}]"
            shape.append(n)
    meta = dict(typ=typ, dims=dims, sizes=sizes, attrs=attrs, latd=latd, lond=lond, stride=stride,
                lat=lat[::stride], lon=lon[::stride], ce=ce, shape=shape, count=int(np.prod(shape)))
    _DAP_CACHE[key] = meta
    return meta


def _array_bytes(typ, count):
    dtype, size = DAP_TYPES[typ]
    n = count * size
    return dtype, (n + 3) // 4 * 4 if typ == "Byte" else n


def parse_dods_multi(blob, specs):
    """Several arrays one after another (XDR). specs = [(typ, count)]. Returns list of arrays; checks everything is consumed."""
    i = blob.find(b"\nData:\n")
    if i < 0:
        raise ValueError("no Data marker; response starts " + repr(blob[:150]))
    p = i + len(b"\nData:\n")
    out = []
    for typ, count in specs:
        n1, n2 = struct.unpack(">II", blob[p:p + 8])
        if n1 != n2 or n1 != count:
            raise ValueError(f"unexpected element count {n1} (wanted {count})")
        p += 8
        dtype, nbytes = _array_bytes(typ, count)
        item = np.dtype(dtype).itemsize
        out.append(np.frombuffer(blob[p:p + count * item], dtype=dtype))
        p += nbytes
    if p != len(blob):
        raise ValueError(f"{len(blob)-p} unexpected trailing bytes (Grid maps in the response?)")
    return out


def _postprocess(arr, meta):
    arr = arr.astype(float).reshape(meta["shape"])
    a = meta["attrs"]
    for k in ("_FillValue", "missing_value"):
        if k in a:
            arr[arr == a[k][0]] = np.nan
    if "valid_range" in a and len(a["valid_range"]) >= 2:
        arr[(arr < a["valid_range"][0]) | (arr > a["valid_range"][1])] = np.nan
    if "valid_min" in a:
        arr[arr < a["valid_min"][0]] = np.nan
    if "valid_max" in a:
        arr[arr > a["valid_max"][0]] = np.nan
    arr = arr * (a["scale_factor"][0] if "scale_factor" in a else 1.0) + (a["add_offset"][0] if "add_offset" in a else 0.0)
    arr, lat, lon = finish(arr, meta["dims"], meta["latd"], meta["lond"], meta["lat"], meta["lon"])
    return arr, lat, lon, str(a.get("units", "")), str(a.get("long_name", ""))


def read_fields_dap(session, url, varnames, stride_req=0, batch=10):
    """Read many variables of one granule with few requests. Returns (fields, errors)."""
    fields, errors, metas = {}, {}, {}
    for v in varnames:
        try:
            metas[v] = dap_meta(session, url, v, stride_req)
        except Exception as e:
            errors[v] = e
    names = list(metas)
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        done = False
        if len(chunk) > 1 and not _DAP_TEXT.get(("nobatch", _ckey(url))):
            try:
                proj = ",".join(f"{v}.{v}{metas[v]['ce']}" for v in chunk)
                raw = _get(session, f"{url}.dods?{proj}", "batch").content
                arrs = parse_dods_multi(raw, [(metas[v]["typ"], metas[v]["count"]) for v in chunk])
                for v, arr in zip(chunk, arrs):
                    fields[v] = _postprocess(arr, metas[v])
                done = True
            except Exception as e:
                _DAP_TEXT[("nobatch", _ckey(url))] = str(e)[:100]
        if not done:
            for v in chunk:
                try:
                    fields[v] = read_field_dap(session, url, v, stride_req)
                except Exception as e:
                    errors[v] = e
    return fields, errors


def read_field_dap(session, url, var, stride_req=0):
    """One variable per request (fallback path)."""
    meta = dap_meta(session, url, var, stride_req)
    last = None
    for dotted in (True, False):
        proj = f"{var}.{var}{meta['ce']}" if dotted else f"{var}{meta['ce']}"
        try:
            raw = _get(session, f"{url}.dods?{proj}", var).content
            arr = parse_dods(raw, DAP_TYPES[meta["typ"]][0], meta["count"])
            return _postprocess(arr, meta)
        except Exception as e:
            last = e
    raise last


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
def process_granule(earthaccess, result, rows, mode, state, stride=0):
    """Returns ({variable: 5deg array}, info, meta). Per variable: OPeNDAP first, then (auto) a file download
    for whatever OPeNDAP could not deliver."""
    t0 = time.time()
    fields, info, failed = {}, {}, []
    use_dap = mode in ("auto", "opendap") and not state.get("no_opendap")
    use_stream = mode == "stream"
    if use_dap:
        try:
            if "session" not in state:
                state["session"] = earthaccess.get_requests_https_session()
            url = opendap_url(result)
        except Exception as e:
            if mode == "opendap":
                raise
            state["no_opendap"] = True
            print(f"  OPeNDAP not available for this product ({type(e).__name__}: {str(e)[:90]}); using downloads")
            use_dap = False
    if use_dap:
        got, errs = read_fields_dap(state["session"], url, [r["variable"] for r in rows], stride)
        fields.update(got)
        if errs and mode == "opendap":
            raise next(iter(errs.values()))
        for r in rows:
            if r["variable"] in errs:
                failed.append(r)
                e = errs[r["variable"]]
                if r["variable"] not in state.setdefault("reported", set()):
                    state["reported"].add(r["variable"])
                    print(f"  {r['variable']}: OPeNDAP failed ({type(e).__name__}: {str(e)[:90]}); will download the file")
        info["how"] = "opendap" if not failed else "opendap+download"
    elif use_stream:
        fobj = earthaccess.open([result])[0]
        try:
            fields = {r["variable"]: read_field_h5(fobj, r["hdf_group"], r["variable"]) for r in rows}
        finally:
            try:
                fobj.close()
            except Exception:
                pass
        info["how"] = "stream"
    else:
        failed = list(rows)
        info["how"] = "download"
    if failed and mode != "opendap":
        tmp = tempfile.mkdtemp(prefix="extract_")
        try:
            files = earthaccess.download([result], tmp, show_progress=False)
            if not files:
                raise RuntimeError("download returned no file")
            path = str(files[0])
            info["size_mb"] = os.path.getsize(path) / 1e6
            for r in failed:
                fields[r["variable"]] = read_field(path, r["hdf_group"], r["variable"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out, meta = {}, {}
    for name, (arr, lat, lon, units, ln) in fields.items():
        key = (len(lat), len(lon), float(lat[0]), float(lon[0]))
        if state.get("grid") != key:
            state["idx"], state["w"] = cell_index(lat, lon)
            state["grid"] = key
        out[name] = coarsen(arr, state["idx"], state["w"])
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


def _job(result, rows, mode, cache, m, stride):
    out, info, _ = process_granule(_EA, result, rows, mode, _STATE, stride)
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
        out, info, meta = process_granule(earthaccess, by_month[pick[0]], rows, a.mode, state, a.stride)
        nxt = [m for m in months if m > pick[0]][:1]
        info2 = None
        if nxt:
            _, info2, _ = process_granule(earthaccess, by_month[nxt[0]], rows, a.mode, state, a.stride)
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
        per = (info2 or info)["seconds"]
        print(f"\nPROBE: mode={info['how']}")
        print(f"  first granule ({pick[0]}): {info['seconds']:.1f}s (includes one-time set-up)")
        if info2:
            print(f"  second granule ({nxt[0]}): {info2['seconds']:.1f}s  <- the steady-state cost per month")
        print(f"Estimated {product}, {n} months: ~{per*n/60/a.workers:.0f} min with {a.workers} workers "
              f"(if the server does not slow down under parallel load)")
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
        futs = {ex.submit(_job, by_month[m], rows, a.mode, cache, m, a.stride): m for m in todo}
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
    ap.add_argument("--skip", nargs="+", default=[], help="with --all: leave these products out (run them later)")
    ap.add_argument("--vars", nargs="*", default=None, help="only these variables (single product only)")
    ap.add_argument("--start", default="2005-01")
    ap.add_argument("--end", default="2024-12")
    ap.add_argument("--out", default="data")
    ap.add_argument("--mode", choices=["auto", "opendap", "stream", "download"], default="auto")
    ap.add_argument("--stride", type=int, default=0, help="OPeNDAP: take every Nth native point (0 = auto, aim for ~0.25 deg spacing)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--probe", action="store_true", help="one granule only; writes nothing")
    ap.add_argument("--force", action="store_true", help="ignore cache / finished outputs")
    a = ap.parse_args()

    prods = load_pool(a.pool)
    names = [p for p in prods if p not in set(a.skip)] if a.all else (a.product or [])
    if a.skip:
        unknown = [p for p in a.skip if p not in prods]
        if unknown:
            print(f"note: --skip names not in the pool: {unknown}")
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
