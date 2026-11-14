#!/usr/bin/env python3
"""Can we read ONE variable of ONE monthly granule through NASA's OPeNDAP service (a few hundred KB, not 54 MB)?

Writes nothing. Usage (venv active, earthaccess installed):
    python probe_opendap.py                                   # MERRA-2 T2M, June 2015
    python probe_opendap.py --product M2TMNXSLV --var T2M --month 201506

It tries every OPeNDAP address it can find for the granule and reports, for each, whether the login works,
how many bytes came back and how long it took. Only `requests` and `numpy` are needed (no pydap/xarray).
Compare with the earlier file probe: native range 206..311.9, native mean 280.2, 54 MB in ~13 s.
"""
import argparse
import re
import struct
import sys
import time

import numpy as np


def parse_dds(text, var):
    """DDS text -> (dim names, sizes) of `var`, or None."""
    m = re.search(r"(?:Float32|Float64|Int16|Int32|UInt16|UInt32|Byte)\s+" + re.escape(var) + r"((?:\[[^\]]+\])+);", text)
    if not m:
        return None
    dims = re.findall(r"\[(\w+)\s*=\s*(\d+)\]", m.group(1))
    return [d for d, _ in dims], [int(n) for _, n in dims]


def parse_dods_first_array(blob, dtype=">f4"):
    """DAP2 .dods response -> first array (XDR: uint32 count twice, then big-endian values)."""
    i = blob.find(b"\nData:\n")
    if i < 0:
        raise ValueError("no 'Data:' marker; response starts: " + repr(blob[:200]))
    p = i + len(b"\nData:\n")
    n1, n2 = struct.unpack(">II", blob[p:p + 8])
    if n1 != n2:
        raise ValueError("bad XDR length header")
    p += 8
    size = np.dtype(dtype).itemsize
    return np.frombuffer(blob[p:p + n1 * size], dtype=dtype)


def candidate_urls(result):
    """OPeNDAP addresses for a granule: from CMR metadata, plus the usual rewrites of the data link."""
    urls = []
    for u in result["umm"].get("RelatedUrls", []):
        link = u.get("URL", "")
        if "opendap" in link.lower() or "OPENDAP" in str(u.get("Subtype", "")).upper():
            urls.append(link)
    for d in result.data_links():
        for a, b in (("/data/", "/opendap/"),):
            if a in d:
                urls.append(d.replace(a, b))
        urls.append(re.sub(r"https://data\.gesdisc\.earthdata\.nasa\.gov/data/", "https://data.gesdisc.earthdata.nasa.gov/opendap/", d))
    out = []
    for u in urls:
        for suf in (".html", ".dds", ".das", ".dods"):
            if u.endswith(suf):
                u = u[: -len(suf)]
        if u not in out:
            out.append(u)
    return out


def get_session(earthaccess):
    for name in ("get_requests_https_session",):
        f = getattr(earthaccess, name, None)
        if f:
            return f()
    return earthaccess.__auth__.get_session()


def try_url(session, url, var):
    t0 = time.time()
    r = session.get(url + ".dds", timeout=60)
    print(f"    .dds -> HTTP {r.status_code} ({time.time()-t0:.1f}s, final URL {r.url[:90]})")
    if r.status_code != 200 or "Dataset" not in r.text[:100]:
        print("    first bytes:", repr(r.text[:150]))
        return None
    info = parse_dds(r.text, var)
    if not info:
        print(f"    variable {var} not found in DDS; DDS starts: {r.text[:200]!r}")
        return None
    dims, sizes = info
    ce = "".join(f"[0:{n-1}]" for n in sizes)
    print(f"    {var} dims {dims} sizes {sizes}")
    for proj in (f"{var}.{var}{ce}", f"{var}{ce}"):
        t1 = time.time()
        d = session.get(f"{url}.dods?{proj}", timeout=300)
        dt = time.time() - t1
        print(f"    .dods?{proj} -> HTTP {d.status_code}, {len(d.content)/1e3:.0f} KB in {dt:.1f}s")
        if d.status_code == 200:
            try:
                arr = parse_dods_first_array(d.content)
            except Exception as e:
                print("    parse failed:", e)
                continue
            if arr.size == int(np.prod(sizes)):
                return arr.reshape(sizes), dt, len(d.content)
            print(f"    unexpected element count {arr.size} vs {int(np.prod(sizes))}")
        else:
            print("    body:", repr(d.content[:150]))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="M2TMNXSLV")
    ap.add_argument("--var", default="T2M")
    ap.add_argument("--month", default="201506")
    a = ap.parse_args()
    import earthaccess
    earthaccess.login(strategy="all", persist=True)
    y, m = int(a.month[:4]), int(a.month[4:])
    res = earthaccess.search_data(short_name=a.product, temporal=(f"{y}-{m:02d}-01", f"{y}-{m:02d}-28"), count=3)
    if not res:
        sys.exit("granule not found")
    r = res[0]
    print("granule:", r["umm"].get("GranuleUR"))
    cands = candidate_urls(r)
    print(f"{len(cands)} candidate OPeNDAP address(es):")
    for c in cands:
        print("  ", c)
    if not cands:
        print("No OPeNDAP address found in the metadata. Data links were:", r.data_links())
        return 1
    s = get_session(earthaccess)
    for c in cands[:5]:
        print("\ntrying", c)
        try:
            out = try_url(s, c, a.var)
        except Exception as e:
            print("    error:", type(e).__name__, str(e)[:200])
            continue
        if out:
            arr, dt, nbytes = out
            v = np.where(np.abs(arr) > 1e10, np.nan, arr.astype(float))
            print(f"\nWORKS: {nbytes/1e3:.0f} KB in {dt:.1f}s (vs ~54,000 KB in ~13 s for the whole file)")
            print(f"values: shape {arr.shape}, range {np.nanmin(v):.4g}..{np.nanmax(v):.4g}, mean {np.nanmean(v):.4g}"
                  f"  (file probe for T2M June 2015 said range 206..311.9, mean 280.2)")
            print(f"For 240 months: ~{dt*240/60:.0f} min per variable, one variable per request.")
            return 0
    print("\nNone of the addresses worked. Send me the output above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
