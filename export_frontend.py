#!/usr/bin/env python3
"""Stage G: export everything the app needs as small static JSON files in public/data/.

  manifest.json          variables (definition, units, source, global result), IPCC region list, hotspots index, notes
  maps/<slug>.json       5-degree grids: trend per decade, FDR-significance, p-value, effect size
  series/<slug>.json     monthly series + trend statistics for the globe, the IPCC regions and the variable's hotspots
  tiles/<slug>.bin|json  per-tile monthly series, for areas drawn in the app
  interesting.json       early signs: trends that just miss the strict test but are consistent over time
All numbers are converted to display units once here (factor/offset below), so the app never converts anything.

Usage: python export_frontend.py
"""
import json
import os
import shutil

import numpy as np
from scipy.stats import theilslopes

from trends import bh_fdr

OUT = "public/data"

# slug, display name, plain definition, display units, factor (native -> display), raw offset (series only),
# colour scheme hint, category, dataset / attribution.  Definitions are written for students; verify before submitting.
V = {
    "M2TMNXSLV.T2M": ("t2m", "Near-surface air temperature",
        "Air temperature about 2 m above the ground or sea surface. It comes from MERRA-2, a global model that blends satellite and ground observations.",
        "°C", 1, -273.15, "heat", "Atmosphere", "MERRA-2 monthly means (M2TMNXSLV), NASA GMAO, via NASA GES DISC"),
    "REYNOLDS_NCDC_L4_MONTHLY_V5.sst": ("sst", "Sea surface temperature",
        "Temperature of the top layer of the ocean, a reconstruction (ERSST v5) from ship, buoy and satellite-era records on a 2° grid.",
        "°C", 1, 0, "heat", "Ocean", "ERSST v5 (NOAA NCDC) as distributed by NASA PO.DAAC (REYNOLDS_NCDC_L4_MONTHLY_V5)"),
    "NASA_SSH_REF_SIMPLE_GRID_V11.ssha": ("sea_level", "Sea level (height anomaly)",
        "How much higher or lower the sea surface is than its long-term average, measured by satellite radar altimeters.",
        "cm", 100, 0, "neutral", "Ocean", "NASA-SSH Simple Gridded Sea Surface Height v1.1 (NASA PO.DAAC)"),
    "GPM_3IMERGM.precipitation": ("precip", "Precipitation rate",
        "How much rain and snow falls, averaged per day, from a merged estimate of satellite microwave and infrared sensors with rain-gauge correction.",
        "mm/day", 24, 0, "water", "Water cycle", "GPM IMERG monthly (GPM_3IMERGM), NASA GES DISC"),
    "MOD10CM.Snow_Cover_Monthly_CMG": ("snow", "Snow cover",
        "The share of each grid cell that is covered by snow in a month, from MODIS on the Terra satellite (0 to 100%).",
        "% of area", 1, 0, "water", "Cryosphere", "MODIS/Terra Snow Cover Monthly L3 Global 0.05° (MOD10CM), NASA NSIDC DAAC"),
    "MOD13C2.CMG 0.05 Deg Monthly NDVI": ("ndvi", "Vegetation greenness (NDVI)",
        "An index of how green and dense plant cover is. Higher values mean more healthy vegetation; bare ground and water are near zero or below.",
        "index", 1, 0, "green", "Land", "MODIS/Terra Vegetation Indices Monthly L3 Global 0.05° (MOD13C2), NASA LP DAAC"),
    "GLDAS_CLSM10_M.TWS_inst": ("tws", "Terrestrial water storage",
        "All the water held on land (soil water, groundwater, snow and surface water), as simulated by a land model. In mm of water.",
        "mm of water", 1, 0, "water", "Land", "GLDAS Catchment land model monthly (GLDAS_CLSM10_M), NASA GES DISC"),
    "M2TMNXRAD.SWGDN": ("sw_down", "Sunlight reaching the surface",
        "Incoming shortwave (solar) energy that reaches the ground or sea, averaged over the month.",
        "W/m²", 1, 0, "neutral", "Atmosphere", "MERRA-2 monthly radiation (M2TMNXRAD), NASA GMAO, via NASA GES DISC"),
    "M2TMNXLND.GWETTOP": ("soil_wetness_top", "Surface soil wetness",
        "How full of water the top soil layer is, from 0 (dry) to 1 (saturated).",
        "fraction (0–1)", 1, 0, "water", "Land", "MERRA-2 land surface (M2TMNXLND), NASA GMAO, via NASA GES DISC"),
    "GLDAS_VIC10_M.Swnet_tavg": ("sw_net", "Sunlight absorbed by land",
        "Net shortwave (solar) energy absorbed by the land surface: incoming sunlight minus what is reflected.",
        "W/m²", 1, 0, "neutral", "Land", "GLDAS VIC land model monthly (GLDAS_VIC10_M), NASA GES DISC"),
    "M2TMNXAER.TOTEXTTAU": ("aod", "Aerosol optical depth",
        "How much sunlight is blocked by tiny airborne particles such as dust, smoke, sea salt and pollution. Higher means hazier air.",
        "index", 1, 0, "neutral", "Atmosphere", "MERRA-2 aerosol diagnostics (M2TMNXAER), NASA GMAO, via NASA GES DISC"),
    "GLDAS_NOAH025_M.SoilMoi10_40cm_inst": ("soil_moist_10_40", "Soil moisture, 10–40 cm",
        "Water held in the soil layer 10 to 40 cm below the surface (1 kg per m² is about 1 mm of water).",
        "kg/m²", 1, 0, "water", "Land", "GLDAS Noah land model 0.25° monthly (GLDAS_NOAH025_M), NASA GES DISC"),
    "M2TMNXSLV.H500": ("h500", "Height of the 500 hPa level",
        "The altitude (about 5.5 km) where air pressure is 500 hPa. It rises when the air column below warms, so it tracks warming of the lower atmosphere.",
        "m", 1, 0, "heat", "Atmosphere", "MERRA-2 monthly means (M2TMNXSLV), NASA GMAO, via NASA GES DISC"),
    "GLDAS_CLSM10_M.Qle_tavg": ("latent_heat", "Latent heat flux (evaporation energy)",
        "Energy that leaves the land surface as water evaporates. Higher means more evaporation and plant water use.",
        "W/m²", 1, 0, "neutral", "Land", "GLDAS Catchment land model monthly (GLDAS_CLSM10_M), NASA GES DISC"),
    "M2TMNXSLV.CLDTMP": ("cloud_top_temp", "Cloud-top temperature",
        "Temperature at the top of the clouds. Colder tops mean taller clouds.",
        "K", 1, 0, "heat", "Atmosphere", "MERRA-2 monthly means (M2TMNXSLV), NASA GMAO, via NASA GES DISC"),
    "GLDAS_VIC10_M.Qs_acc": ("runoff", "Storm surface runoff",
        "Rain water that runs over the ground surface instead of soaking in (accumulated amount, as provided by the model).",
        "kg/m² (≈ mm)", 1, 0, "water", "Land", "GLDAS VIC land model monthly (GLDAS_VIC10_M), NASA GES DISC"),
    "FLDAS_NOAH01_C_GL_M.Evap_tavg": ("evap_land", "Evapotranspiration (land)",
        "Water returned to the air from soil and plants, averaged per day.",
        "mm/day", 86400, 0, "neutral", "Land", "FLDAS Noah land model monthly (FLDAS_NOAH01_C_GL_M), NASA GES DISC"),
    "GLDAS_NOAH025_M.SoilTMP0_10cm_inst": ("soil_temp", "Soil temperature, top 10 cm",
        "Temperature of the top 10 cm of the soil.",
        "°C", 1, -273.15, "heat", "Land", "GLDAS Noah land model 0.25° monthly (GLDAS_NOAH025_M), NASA GES DISC"),
    "GLDAS_VIC10_M.SoilMoi_depth2_inst": ("soil_moist_vic2", "Soil moisture, VIC middle layer",
        "Water held in the second (middle) soil layer of the VIC land model (1 kg per m² is about 1 mm of water).",
        "kg/m²", 1, 0, "water", "Land", "GLDAS VIC land model monthly (GLDAS_VIC10_M), NASA GES DISC"),
    "M2TMNXFLX.EVAP": ("evap_surface", "Surface evaporation",
        "Water evaporating from the surface into the air, averaged per day (negative values are dew or condensation).",
        "mm/day", 86400, 0, "neutral", "Atmosphere", "MERRA-2 surface flux diagnostics (M2TMNXFLX), NASA GMAO, via NASA GES DISC"),
}


def rnd(x, d=4):
    if x is None:
        return None
    x = float(x)
    return None if not np.isfinite(x) else float(f"{x:.{d}g}")


def conv_series(rec, f, off):
    """apply display conversion to every numeric field of one region/hotspot record"""
    if rec.get("status") != "ok":
        return rec
    rec["raw"] = [None if v is None else rnd(v * f + off, 5) for v in rec["raw"]]
    rec["anomaly"] = [None if v is None else rnd(v * f, 5) for v in rec["anomaly"]]
    for k in ("slope_per_decade", "ols_per_decade", "sen_intercept"):
        rec[k] = rnd(rec[k] * f)
    rec["ci95"] = [rnd(x * f) for x in rec["ci95"]]
    for k in ("mean_cell_slope_per_decade",):
        if k in rec:
            rec[k] = rnd(rec[k] * f)
    if "halves_slope_per_decade" in rec:
        rec["halves_slope_per_decade"] = [rnd(x * f) for x in rec["halves_slope_per_decade"]]
    return rec


def early_sign(r, near):
    """one rule for every region type: just misses the strict test (passes FDR at 10%), 95% CI excludes zero,
    and the trend points the same way in both halves of the record"""
    if r.get("status") != "ok" or r["significant_fdr"] or not near or not r["ci_excludes_zero"]:
        return False
    a = np.array([np.nan if x is None else x for x in r["anomaly"]], float)
    t = np.arange(a.size) / 12.0
    h = a.size // 2
    sg = np.sign(r["slope_per_decade"])
    for sl in (slice(0, h), slice(h, None)):
        m = np.isfinite(a[sl])
        if np.sign(theilslopes(a[sl][m], t[sl][m])[0]) != sg:
            return False
    return True


def near_miss(recs):
    """id -> passes Benjamini-Hochberg at 10% among the non-global tested regions (global is a single test: p < 0.10)"""
    ok = [r for r in recs if r.get("status") == "ok" and r["id"] != "global"]
    q = bh_fdr(np.array([r["p"] for r in ok], float), 0.10) if ok else []
    out = {r["id"]: bool(x) for r, x in zip(ok, q)}
    out["global"] = True
    return out


def sentence(name, vname, units, rec):
    s, (lo, hi), p = rec["slope_per_decade"], rec["ci95"], rec["p"]
    direction = "rising" if s > 0 else "falling"
    return (f"{vname} over {name} is {direction} by {abs(s):.3g} {units} per decade "
            f"(95% confidence interval {lo:+.3g} to {hi:+.3g}, p = {p:.2g}). "
            + ("The interval does not include zero, but the result just misses the strict test, so it could still be chance."
               if rec["ci_excludes_zero"] else "The interval includes zero, so this is only a hint."))


def main():
    sel = json.load(open("data/selection/selection.json"))
    ids = sel["headline"] + sel["data_driven"]
    assert set(ids) == set(V), set(ids) ^ set(V)
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT + "/maps")
    os.makedirs(OUT + "/series")

    variables, hotspot_index = [], {}
    interesting = []
    for vid in ids:
        slug, name, definition, units, f, off, scheme, cat, source = V[vid]
        tr = json.load(open(f"data/trends/{vid}.json"))
        z = np.load(f"data/trends/{vid}.npz")
        raw = np.load(f"data/raw5/{vid}.npz", allow_pickle=True)
        p_cell = z["p_ols"] if tr["test_used"] == "ols" else z["p_mk"]

        # ---- map
        flat = lambda a, ff=1.0, d=4: [None if not np.isfinite(x) else rnd(x * ff, d) for x in a.ravel()]
        sl = z["slope"] * f
        lim = float(np.nanpercentile(np.abs(sl[z["sig"]]), 95)) if z["sig"].any() else float(np.nanpercentile(np.abs(sl), 95))
        json.dump(dict(var=slug, lat=[float(x) for x in z["lat"]], lon=[float(x) for x in z["lon"]],
                       units_per_decade=units + " per decade", color_limit=rnd(lim, 3),
                       slope=flat(z["slope"], f), significant=[int(x) for x in z["sig"].ravel()],
                       p=flat(p_cell, 1.0, 3), effect_size=flat(z["snr"], 1.0, 3)),
                  open(f"{OUT}/maps/{slug}.json", "w"), separators=(",", ":"))

        # ---- per-tile monthly series (display units) as 16-bit integers, for areas drawn in the app
        os.makedirs(OUT + "/tiles", exist_ok=True)
        cube = raw["data"].astype(np.float64) * f + off                       # (T, NY, NX)
        T_, NY_, NX_ = cube.shape
        flat_t = cube.reshape(T_, NY_ * NX_).T                                 # (tiles, T)
        lo_ = np.nanmin(np.where(np.isfinite(flat_t), flat_t, np.nan), axis=1)
        hi_ = np.nanmax(np.where(np.isfinite(flat_t), flat_t, np.nan), axis=1)
        lo_ = np.where(np.isfinite(lo_), lo_, 0.0)
        hi_ = np.where(np.isfinite(hi_), hi_, 0.0)
        scale_ = np.where(hi_ > lo_, (hi_ - lo_) / 65000.0, 1.0)
        q_ = np.where(np.isfinite(flat_t), np.round((flat_t - lo_[:, None]) / scale_[:, None]) - 32500, -32768).astype("<i2")
        with open(f"{OUT}/tiles/{slug}.bin", "wb") as fh:
            fh.write(lo_.astype("<f4").tobytes() + scale_.astype("<f4").tobytes() + q_.tobytes())
        json.dump(dict(months=[int(m) for m in raw["months"]], nlat=int(NY_), nlon=int(NX_),
                       lat0=float(raw["lat"][0]), lon0=float(raw["lon"][0]), step=5.0),
                  open(f"{OUT}/tiles/{slug}.json", "w"), separators=(",", ":"))

        # ---- series: regions + hotspots
        rg = json.load(open(f"data/regional/{vid}.json"))
        hs = json.load(open(f"data/hotspots/{vid}.json"))
        regions = [conv_series(r, f, off) for r in rg["regions"] if r["id"] == "global"]   # the globe; the fixed regions are the IPCC ones
        hots = [conv_series(h, f, off) for h in hs["hotspots"]]
        ipcc = [conv_series(r, f, off) for r in json.load(open(f"data/regional_ipcc/{vid}.json"))["regions"]]
        for h in hots:
            h["cells"] = [[a, b] for a, b in h["cells"]]
        json.dump(dict(var=slug, units=units, months_start=rg["t0"], months_end=rg["t1"],
                       fdr_family="the global mean is one pre-specified test",
                       ipcc_fdr_family="the IPCC regions of this variable that have enough tiles",
                       regions=regions, ipcc=ipcc, hotspots=hots),
                  open(f"{OUT}/series/{slug}.json", "w"), separators=(",", ":"))

        # ---- manifest entry
        g = next(r for r in regions if r["id"] == "global")
        gs = g["slope_per_decade"] if g.get("status") == "ok" else tr["global_slope_per_decade"] * f
        finding = (f"Globally {'rising' if gs > 0 else 'falling'} by {abs(gs):.3g} {units} per decade"
                   + (" (statistically significant)" if g.get("significant_fdr") else " (not significant on its own)")
                   + f"; {100 * tr['sig_area_fraction']:.0f}% of the area has a significant trend "
                   f"({100 * tr['sig_positive_area']:.0f}% rising, {100 * tr['sig_negative_area']:.0f}% falling).")
        variables.append(dict(
            id=slug, var_id=vid, name=name, definition=definition, units=units, category=cat, family=sel["meta"][vid]["family"],
            role=sel["roles"][vid], scheme=scheme, source=source, record="monthly, 2005–2024 (240 months)"
            if int(raw["months"].size) == 240 else f"monthly, 2005–2024 ({int(raw['months'].size)} months)",
            grid="5° x 5°", test_used=tr["test_used"], map_color_limit=rnd(lim, 3),
            global_slope_per_decade=rnd(gs), global_ci95=g.get("ci95"), global_p=g.get("p"),
            sig_area_fraction=tr["sig_area_fraction"], sig_positive_area=tr["sig_positive_area"],
            sig_negative_area=tr["sig_negative_area"], divergence=tr["divergence"], finding=finding,
            stability=sel["stability"].get(vid), drop_one_loss=rnd(sel["drop_one"].get(vid), 3)))
        hotspot_index[slug] = [dict(id=h["id"], name=h["name"], direction=h["direction"], bbox=h["bbox"],
                                    centroid=h["centroid"], n_cells=h["n_cells"], slope_per_decade=h["slope_per_decade"],
                                    ci95=h["ci95"], p=h["p"], consistent_in_both_halves=h["consistent_in_both_halves"],
                                    exploratory=True) for h in hots]
        if g.get("status") == "ok" and g["p"] < 0.10 and early_sign(g, True):
            interesting.append(dict(var=slug, var_name=name, units=units, region="global", region_name="Global",
                                    slope_per_decade=g["slope_per_decade"], ci95=g["ci95"], p=g["p"], snr=g["snr"],
                                    ci_excludes_zero=g["ci_excludes_zero"], text=sentence("the globe", name, units, g)))

    interesting.sort(key=lambda r: r["p"])
    # ---- early signs among the IPCC regions: a tighter rule, because ~970 tests run and ~10% would pass p < 0.10 by chance.
    # Kept only if it (1) just misses the strict test but passes FDR at 10%, (2) has a 95% CI that excludes zero, and
    # (3) points the same way in both halves of the record.
    for it in interesting:
        it["group"] = "global"
    n_ipcc = 0
    for vid in ids:
        slug, name, _d, units, f, _o, *_ = V[vid]
        recs = json.load(open(f"data/regional_ipcc/{vid}.json"))["regions"]
        nm = near_miss(recs)
        for r in recs:
            if not early_sign(r, nm.get(r["id"], False)):
                continue
            s_, (lo, hi), p_ = r["slope_per_decade"] * f, [x * f for x in r["ci95"]], r["p"]
            interesting.append(dict(
                var=slug, var_name=name, units=units, region=r["id"], region_name=r["name"], group="ipcc",
                slope_per_decade=rnd(s_), ci95=[rnd(lo), rnd(hi)], p=p_, snr=r["snr"], ci_excludes_zero=True,
                text=f"{name} over {r['name']} is {'rising' if s_ > 0 else 'falling'} by {abs(s_):.3g} {units} per decade "
                     f"(95% confidence interval {lo:+.3g} to {hi:+.3g}, p = {p_:.2g}). It narrowly misses the strict test, "
                     "but the direction is the same in both halves of the record."))
            n_ipcc += 1
    print(f"early signs: {len(interesting) - n_ipcc} global + {n_ipcc} IPCC")
    json.dump(dict(criteria="passes FDR at 10% but not at 5%, 95% CI excludes zero, same direction in both halves of the record (same rule for the globe and the IPCC regions)", items=interesting),
              open(f"{OUT}/interesting.json", "w"), indent=1)

    # ---- IPCC AR6 reference regions: outlines + which region each tile belongs to
    shutil.copy("data/ipcc_regions.geojson", f"{OUT}/ipcc_regions.geojson")
    shutil.copy("data/ipcc_tiles.json", f"{OUT}/ipcc_tiles.json")
    ipcc_out = [dict(id=f["properties"]["id"], abbrev=f["properties"]["abbrev"], name=f["properties"]["name"],
                     kind=f["properties"]["kind"], n_tiles=f["properties"]["n_tiles"])
                for f in json.load(open("data/ipcc_regions.geojson"))["features"]]

    json.dump(dict(
        title="Earth System Trend Detective", window="2005-01 to 2024-12 (monthly)", grid="5° x 5°",
        methods=dict(
            anomalies="Monthly values minus the average for the same calendar month, so seasons do not look like trends.",
            rate="Sen slope (median of all pairwise slopes) per decade with a 95% confidence interval.",
            tests="Mann-Kendall test with the variance inflated for month-to-month autocorrelation (lag-1), or an OLS t-test when the residuals pass Durbin-Watson and Shapiro checks (in practice Mann-Kendall was used for every variable).",
            multiple_testing="Benjamini-Hochberg false discovery rate at 5%: across cells for maps, and across the IPCC regions for each variable (the global mean is one separate test).",
            effect_size="Total change over the record divided by the month-to-month noise (SD of detrended anomalies)."),
        caveats=[
            "Twenty years is short; trends can reflect natural variability such as El Niño, not only long-term change.",
            "The Mann-Kendall correction is slightly liberal (about 6% false positives at a nominal 5% in simulation).",
            "Regions and drawn boxes are averages of whole 5° tiles (a tile counts when its centre is inside), so small areas are coarse and regions with fewer than 3 tiles of data are not tested.",
            "Hotspots are chosen because their cells look significant, so their p-values are optimistic (exploratory).",
            "Land models disagree with each other for some variables; this is shown, not hidden.",
            "Variables were selected by a data-driven method plus six hand-picked headline variables; see 'role'."],
        not_available="AIRS products, MOD21C3 and tropospheric ozone were not used. Snow cover has 238 of 240 months.",
        variables=variables, ipcc_regions=ipcc_out, hotspots=hotspot_index),
        open(f"{OUT}/manifest.json", "w"), indent=1)
    sizes = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs)
    print(f"exported {len(variables)} variables, {len(ipcc_out)} IPCC regions, {sum(len(v) for v in hotspot_index.values())} hotspots, "
          f"{len(interesting)} early signs; {sizes/1e6:.2f} MB in {OUT}")


if __name__ == "__main__":
    main()
