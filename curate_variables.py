#!/usr/bin/env python3
"""Curate variable_catalog.csv -> variable_pool.csv (the candidate pool for selection).

Decisions encoded (agreed 2026-11-14):
  1. drop MERRA-2 'Var_*' variance fields and helper / QC fields (view angles, counts, errors, ...)
  2. same quantity in several MERRA-2 collections: keep one copy, prefer the time-averaged product;
     instantaneous (M2IMNX*) and statistics products are dropped unless they hold something unique
  3. drop: pressure-level (Np) products, MLS, AIRS3QPM, MOD28C3, GPROF F16, ClimFiSP
     keep OLR (AIRSIL3MSOLR) with the ascending/descending orbit passes averaged
  4. keep ALL five land models (GLDAS CLSM/Noah/VIC, FLDAS, MERRA-2 land) with a symmetric headline list
  5. headline list per product (SPEC below). It is plain data: edit it and re-run.

Usage:
    python curate_variables.py variable_catalog.csv
    python curate_variables.py variable_catalog.csv --out-dir results

Writes:
    variable_pool.csv           the candidate pool (one row per variable, with family + extraction hints)
    variable_pool_dropped.csv   every other catalog row with the reason it was left out (audit trail)
Prints any SPEC entry that is not found in the catalog and any variable name used twice.
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

# product -> [(family, [variables])]; product order = priority when a name appears twice
SPEC = {
    "M2TMNXSLV": [
        ("Temperature", ["T2M", "TS", "T250", "T500", "T850", "TROPT"]),
        ("Humidity & clouds", ["QV2M", "TQV", "TQL", "TQI", "CLDTMP", "CLDPRS"]),
        ("Pressure & circulation", ["SLP", "PS", "H500", "OMEGA500", "U10M", "V10M", "TROPPB"]),
        ("Ozone", ["TO3"]),
    ],
    "M2SMNXSLV": [
        ("Temperature extremes", ["T2MMAX", "T2MMIN"]),
        ("Precipitation", ["TPRECMAX", "HOURNORAIN"]),
    ],
    "M2TMNXOCN": [
        ("Ocean & sea ice", ["TSKINWTR", "TSKINICE", "FRSEAICE", "EFLUXWTR", "HFLUXWTR", "RAINOCN"]),
    ],
    "M2TMNXFLX": [
        ("Precipitation", ["PRECTOTCORR", "PRECSNO"]),
        ("Surface fluxes", ["EFLUX", "HFLUX", "EVAP", "SPEED"]),
        ("Boundary layer", ["PBLH"]),
    ],
    "M2TMNXRAD": [
        ("Clouds", ["CLDTOT", "CLDHGH", "CLDMID", "CLDLOW", "TAUTOT"]),
        ("Radiation", ["ALBEDO", "SWGDN", "SWGNT", "LWGNT", "LWTUP", "LWTUPCLR", "SWTNT", "SWTNTCLR"]),
    ],
    "M2TMNXLND": [
        ("Soil moisture", ["GWETROOT", "GWETTOP", "GWETPROF", "TWLAND"]),
        ("Snow", ["SNOMAS", "SNODP", "FRSNO"]),
        ("Runoff", ["RUNOFF", "BASEFLOW"]),
        ("Vegetation", ["LAI", "GRN"]),
        ("Land energy", ["TSOIL1", "TSURF", "EVPTRNS"]),
    ],
    "M2TMNXGLC": [("Land ice", ["SNOMAS_GL", "SNOWDP_GL", "SNICEALB"])],
    "M2TMNXINT": [
        ("Precipitation", ["PRECCU", "PRECLS"]),
        ("Moisture transport", ["UFLXQV", "VFLXQV"]),
    ],
    "M2TMNXAER": [
        ("Aerosol optical depth", ["TOTEXTTAU", "DUEXTTAU", "SSEXTTAU", "SUEXTTAU", "OCEXTTAU", "BCEXTTAU", "TOTANGSTR"]),
        ("Aerosol mass", ["DUCMASS", "SSCMASS", "SO4CMASS", "OCCMASS", "BCCMASS"]),
    ],
    "M2TMNXADG": [("Aerosol indices", ["DUAERIDX", "SSAERIDX"])],
    "M2TMNXCHM": [("Carbon monoxide", ["COCL", "COSC"])],
    "AIRS3STM": [  # ascending pass (~1:30 pm); descending (_D), TqJ and *_ct (counts) left out
        ("Temperature", ["SurfSkinTemp_A", "SurfAirTemp_A", "TropTemp_A"]),
        ("Humidity & clouds", ["TotH2OVap_A", "H2O_MMR_Surf_A", "RelHumSurf_A", "CloudFrc_A",
                               "CloudTopPres_A", "CloudTopTemp_A", "TotCldLiqH2O_MW_A"]),
        ("Pressure & circulation", ["TropPres_A", "TropHeight_A"]),
        ("Ozone", ["TotO3_A"]),
    ],
    "AIRS3SPM": [
        ("Clouds", ["ice_cld_opt_dpth_A", "ice_cld_eff_diam_A"]),
        ("Boundary layer", ["bndry_lyr_top_A"]),
        ("Ocean", ["MWSST_A"]),
        ("Precipitation", ["IR_Precip_Est_A"]),
    ],
    "AIRSIL3MSOLR": [("Radiation", ["olr", "olr_clr"])],
    "TrCO3_Monthly_OMIMLS": [("Ozone", ["TropoO3"])],
    "GPM_3IMERGM": [("Precipitation", ["precipitation"])],
    "GPCPMON": [("Precipitation", ["sat_gauge_precip"])],
    "MOD11C3": [("Land surface temperature", ["LST_Day_CMG", "LST_Night_CMG"])],
    "MOD21C3": [("Land surface temperature", ["LST_Day", "LST_Night"])],
    "MOD13C2": [("Vegetation", ["CMG 0.05 Deg Monthly NDVI", "CMG 0.05 Deg Monthly EVI"])],
    "MICASA_FLUX_M": [("Carbon fluxes", ["NPP", "Rh", "NEE", "FIRE"])],
    # ocean / ice (added 2026-11-14 after the second catalog run)
    "REYNOLDS_NCDC_L4_MONTHLY_V5": [("Ocean & sea ice", ["sst"])],   # ssta dropped: same signal minus climatology
    "NASA_SSH_REF_SIMPLE_GRID_V11": [("Ocean & sea ice", ["ssha"])],
    "MOD10CM": [("Snow", ["Snow_Cover_Monthly_CMG"])],
    # five land models, symmetric headline families
    "GLDAS_NOAH025_M": [
        ("Land water & energy fluxes", ["Evap_tavg", "Qle_tavg", "Qh_tavg", "Swnet_tavg", "Lwnet_tavg", "Tveg_tavg"]),
        ("Runoff", ["Qs_acc", "Qsb_acc"]),
        ("Precipitation", ["Rainf_tavg", "Snowf_tavg"]),
        ("Snow", ["Qsm_acc", "SWE_inst", "SnowDepth_inst", "Albedo_inst"]),
        ("Soil moisture", ["SoilMoi0_10cm_inst", "SoilMoi10_40cm_inst", "SoilMoi40_100cm_inst", "SoilMoi100_200cm_inst", "RootMoist_inst"]),
        ("Land temperature", ["AvgSurfT_inst", "SoilTMP0_10cm_inst"]),
    ],
    "GLDAS_CLSM10_M": [
        ("Land water & energy fluxes", ["Evap_tavg", "Qle_tavg", "Qh_tavg", "Swnet_tavg", "Lwnet_tavg", "TVeg_tavg"]),
        ("Runoff", ["Qs_acc", "Qsb_acc"]),
        ("Precipitation", ["Rainf_tavg", "Snowf_tavg"]),
        ("Snow", ["Qsm_acc", "SWE_inst", "SnowDepth_inst", "Albedo_inst"]),
        ("Soil moisture", ["SoilMoist_S_inst", "SoilMoist_RZ_inst", "SoilMoist_P_inst", "TWS_inst"]),
        ("Land temperature", ["AvgSurfT_inst", "SoilTMP0_10cm_inst"]),
    ],
    "GLDAS_VIC10_M": [
        ("Land water & energy fluxes", ["Evap_tavg", "Qle_tavg", "Qh_tavg", "Swnet_tavg", "Lwnet_tavg", "TVeg_tavg"]),
        ("Runoff", ["Qs_acc", "Qsb_acc"]),
        ("Precipitation", ["Rainf_tavg", "Snowf_tavg"]),
        ("Snow", ["Qsm_acc", "SWE_inst", "SnowDepth_inst", "Albedo_inst"]),
        ("Soil moisture", ["SoilMoi0_30cm_inst", "SoilMoi_depth2_inst", "SoilMoi_depth3_inst", "RootMoist_inst"]),
        ("Land temperature", ["AvgSurfT_inst"]),
    ],
    "FLDAS_NOAH01_C_GL_M": [
        ("Land water & energy fluxes", ["Evap_tavg", "Qle_tavg", "Qh_tavg", "Swnet_tavg", "Lwnet_tavg"]),
        ("Runoff", ["Qs_tavg", "Qsb_tavg"]),
        ("Precipitation", ["Rainf_f_tavg", "Snowf_tavg"]),
        ("Snow", ["SWE_inst", "SnowCover_inst", "SnowDepth_inst"]),
        ("Soil moisture", ["SoilMoi00_10cm_tavg", "SoilMoi10_40cm_tavg", "SoilMoi40_100cm_tavg", "SoilMoi100_200cm_tavg"]),
        ("Land temperature", ["RadT_tavg", "SoilTemp00_10cm_tavg"]),
    ],
}

DROP_PRODUCTS = {
    # decision 3
    "M2IMNPANA": "pressure-level product (decision 3)", "M2IMNPASM": "pressure-level product (decision 3)",
    "M2TMNPCLD": "pressure-level product (decision 3)", "M2TMNPMST": "pressure-level product (decision 3)",
    "M2TMNPTRB": "pressure-level product (decision 3)", "M2TMNPRAD": "pressure-level product (decision 3)",
    "ML3MBHNO3": "MLS product (decision 3)", "ML3MBN2O": "MLS product (decision 3)", "ML3MBSO2": "MLS product (decision 3)",
    "AIRS3QPM": "AIRS quantization product (decision 3)", "MOD28C3": "empty / not a grid (decision 3)",
    "GPM_3GPROFF16SSMIS_CLIM": "single-sensor GPROF, overlaps IMERG/GPCP (decision 3)",
    "SNDRAQIL3SMCFSP": "ClimFiSP: one usable variable only",
    # decision 2
    "M2IMNXASM": "instantaneous duplicate of time-averaged MERRA-2 (decision 2)",
    "M2IMNXLFO": "instantaneous duplicate of time-averaged MERRA-2 (decision 2)",
    "M2IMNXINT": "instantaneous version, remaining fields are not headline (decision 2)",
    "M2IMNXGAS": "AOD analysis overlaps M2TMNXAER total AOD (decision 2)",
    "M2TMNXLFO": "land-surface forcing fields overlap other products (decision 2)",
}

HELPER = re.compile(r"(^|_)(ct|err|nobs|count|qc|qa)($|_)|view_?ang|view_?time|sun zen|pixel rel|pix |Percent_land|Clear_sky|Emis_", re.I)
PRIORITY = ["M2TMNXSLV", "M2SMNXSLV", "M2TMNXOCN", "M2TMNXFLX", "M2TMNXRAD", "M2TMNXLND", "M2TMNXGLC",
            "M2TMNXINT", "M2TMNXAER", "M2TMNXADG", "M2TMNXCHM"]
REDUCE = {("AIRSIL3MSOLR", "olr"): "mean over orbit_pass", ("AIRSIL3MSOLR", "olr_clr"): "mean over orbit_pass"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog")
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.catalog, encoding="utf-8")))
    index = {(r["product"], r["variable"]): r for r in rows if r["status"] != "ERROR"}
    wanted = {}
    for prod, blocks in SPEC.items():
        for fam, names in blocks:
            for n in names:
                wanted[(prod, n)] = fam

    missing = [k for k in wanted if k not in index]
    pool, dropped = [], []
    for r in rows:
        key = (r["product"], r["variable"])
        if r["status"] == "ERROR":
            dropped.append({**r, "dropped_because": "catalog ERROR: " + r["reason"]})
        elif r["product"] in DROP_PRODUCTS:
            dropped.append({**r, "dropped_because": DROP_PRODUCTS[r["product"]]})
        elif r["variable"].startswith("Var_") or "Variance_of" in r["long_name"]:
            dropped.append({**r, "dropped_because": "variance field (decision 1)"})
        elif key in wanted:
            pool.append({
                "var_id": f"{r['product']}.{r['variable']}", "product": r["product"], "variable": r["variable"],
                "long_name": r["long_name"], "units": r["units"], "family": wanted[key],
                "product_group": r["product_group"], "hdf_group": r["hdf_group"], "dims": r["dims"],
                "reduce": REDUCE.get(key, ""), "catalog_status": r["status"],
            })
        elif HELPER.search(r["variable"]) or HELPER.search(r["long_name"]):
            dropped.append({**r, "dropped_because": "helper / QC field (decision 1)"})
        elif r["status"] == "DROP":
            dropped.append({**r, "dropped_because": "catalog DROP: " + r["reason"]})
        else:
            dropped.append({**r, "dropped_because": "not a headline variable (decision 5)"})

    os.makedirs(a.out_dir, exist_ok=True)
    cols = ["var_id", "product", "variable", "long_name", "units", "family", "product_group", "hdf_group",
            "dims", "reduce", "catalog_status"]
    with open(os.path.join(a.out_dir, "variable_pool.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(pool)
    dcols = list(rows[0].keys()) + ["dropped_because"]
    with open(os.path.join(a.out_dir, "variable_pool_dropped.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=dcols, extrasaction="ignore")
        w.writeheader()
        w.writerows(dropped)

    print(f"catalog rows: {len(rows)} -> pool {len(pool)}, dropped {len(dropped)}")
    print("\nPool by product:")
    for p, n in Counter(x["product"] for x in pool).items():
        print(f"  {p:24}{n}")
    print("\nPool by family:")
    for fam, n in Counter(x["family"] for x in pool).most_common():
        print(f"  {fam:30}{n}")
    print("\nWhy rows were dropped:")
    for why, n in Counter(d["dropped_because"].split(" (decision")[0].split(":")[0] for d in dropped).most_common(8):
        print(f"  {n:5}  {why}")
    if missing:
        print("\nWARNING: in SPEC but not in the catalog:", missing)
    names = defaultdict(list)
    for x in pool:
        names[x["variable"]].append(x["product"])
    same = {k: v for k, v in names.items() if len(v) > 1}
    merra_same = {k: v for k, v in same.items() if all(p.startswith("M2") for p in v)}
    if merra_same:
        print("\nWARNING: same MERRA-2 variable name in several collections (check which to keep):", merra_same)
    print("\nNames shared by different models/products (expected for the land models):", len(same) - len(merra_same))
    return 0


if __name__ == "__main__":
    sys.exit(main())
