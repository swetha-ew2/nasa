# Plan: Earth System Trend Detective

Status as of 2026-11-14. Window 2005–2024, monthly, 5° grid (36 x 72). Everything precomputed; static site on Vercel.

## Done
- [x] Candidate pool and variable curation (`select_products.py` … `curate_variables.py`)
- [x] Extraction to 5° (`extract_slice.py`); fixes: OPeNDAP variable order, fill-value matching, DAS path names, MODIS scale conventions
- [x] Range check of every variable (`check_raw5.py`)
- [x] Cell-level trend statistics (`trends.py`): Sen slope + CI, AR(1)-corrected Mann-Kendall, OLS, FDR across cells
- [x] Selection (`selection.py`): 6 headline + 14 data-driven = 20 variables (decision: keep all 20)
- [x] Regional analysis for the 11 app regions + global (`regional.py`)
- [x] Variable-specific hotspots (`hotspots.py`), labelled exploratory

## Next
1. Frontend export: manifest per variable (plain-language definition, units, source, NASA attribution), trend maps, regional + hotspot series and statistics, selection explanation. Small static files.
2. Wire the globe to real data (replace `src/lib/placeholder.ts` and the placeholder catalog). Visual design matters most:
   - diverging colour scale centred on zero, colour-blind safe, symmetric limits per variable
   - sensible polarity per variable (warming red/blue, precipitation brown/green, vegetation green)
   - non-significant cells visibly muted (hatching/transparency), significant ones strong
   - hotspot outlines on the globe, opposite-sign hotspots of one variable shown together
3. Demo examples (2–3 guided stories) and a short "what do you want to investigate?" flow.
4. Show non-significant but interesting trends clearly labelled (e.g. Mediterranean drying, Amazon warming + water loss).
5. Deploy to Vercel (domain optional).
6. Submission write-up: methodology, caveats, NASA datasets used.

## Later (after the above works)
- **Free-drawn boxes:** let the user draw a box on the globe and get the series + trend statistics for it.
  Needs per-cell monthly series for the 20 variables (about 25 MB as int16, or compute in the browser from smaller
  files). Same statistics as `regional.py` (test choice by residual checks); no multiple-testing family, so show the
  p-value with an "exploratory" label.
- Refine hotspot names (currently coarse boxes) and add a land/ocean mask to the export.

## Known caveats (state honestly)
- Mann-Kendall with the AR(1) correction is slightly liberal (about 6% false positives at nominal 5% in simulation).
- 5° coarsening; small boxes are smoothed over whole cells.
- 20 years is short; trends can reflect natural variability (e.g. ENSO).
- Hotspot p-values are optimistic (regions chosen because they look significant).
- Land models disagree (e.g. GLDAS surface temperature trends have opposite signs); show that, do not hide it.
- Not available: AIRS, MOD21C3 (skipped), TrCO3; MOD10CM misses 2 months; M2TMNXADG aerosol indices are all zero in the source.
