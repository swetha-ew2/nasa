# Earth System Trend Detective

An interactive 3D globe for NASA Space Apps 2026 ("Be An Earth System Trend Detective"). It answers: what is changing,
where, how much, and is it statistically significant?

- Globe (MapLibre GL JS, NASA GIBS imagery) coloured by the trend of the chosen variable on a 5-degree grid; cells without
  a significant trend are faded
- 20 variables chosen by a data-driven selection (plus 6 headline variables), each with a plain-language definition
- 11 regions + global, and variable-specific hotspots (exploratory), each with a real time series, Sen slope, 95% interval,
  Mann-Kendall / OLS p-value and effect size
- "Worth watching": trends that did not pass the strict test but are interesting
- Everything is precomputed: the site is static (`public/data`, about 3 MB). Regenerate it with `python export_frontend.py`.

---

## What you need installed

| Tool | Version | Check with |
|---|---|---|
| Node.js | 18 or newer (20/22 recommended) | `node -v` |
| npm | comes with Node | `npm -v` |

Install Node from https://nodejs.org (LTS). Any modern browser with WebGL works
(Chrome, Edge, Firefox, Safari).

**No Earthdata login is needed for this globe.** The satellite imagery comes from
NASA GIBS, which is open. See section 5 for when you will need the login.

## Run it 

```bash
# 1. unzip, then open a terminal in the project folder
cd earth-trend-detective

# 2. install dependencies (first time only, takes about a minute)
npm install

# 3. start the dev server
npm run dev
```

Open the address it prints (normally http://localhost:5173). Edits to files in
`src/` reload the page automatically. Stop the server with `Ctrl + C`.

Other commands:

```bash
npm run build     # type-check and build the static site into dist/
npm run preview   # serve the built dist/ locally to test it
```

## What to try

1. Drag the globe, scroll to zoom. Any manual interaction stops auto-rotation.
2. Click a variable in the left catalog. Matching pins glow, the rest dim.
3. Click a pin. The camera flies there, the region box is outlined, and the panel opens.
4. Change the variable in the panel dropdown. The chart and info update.
5. Toggle "Satellite imagery" and "Auto-rotate" in the top bar.

## Where things live

```
src/
  App.tsx                 page layout and shared state
  components/
    Globe.tsx             globe, pins, region outline, camera moves
    Catalog.tsx           left sidebar: search, category filter, variable cards
    RegionPanel.tsx       right panel: variable picker, chart, stats
    TrendChart.tsx        placeholder SVG chart (swap for Plotly/ECharts later)
  data/
    regions.ts            the pins: name, lat/lon, bounding box, suggested variables
    variables.ts          the catalog: definitions, units, source, status
  lib/placeholder.ts      fake time-series generator (delete when real data arrives)
  styles.css              all styling
```

To add a region, add an entry to `src/data/regions.ts`. To add a variable, add one to
`src/data/variables.ts` and list its id in the regions it applies to.

The names, sources and record lengths in `variables.ts` are placeholders. Check them
against the real NASA collections before presenting them as fact.
he repo go to Settings, Pages, and choose the `gh-pages` branch.

## Troubleshooting

- **Blank or dark-blue globe with no imagery:** the NASA GIBS tiles did not load
  (offline, firewall, or a school/work network blocking the host). Pins and panels
  still work. Check your connection or try another network.
- **Globe does not appear at all:** WebGL may be disabled. Enable hardware
  acceleration in your browser settings.
- **`npm install` fails:** check `node -v` is 18 or newer.
- **Port already in use:** run `npm run dev -- --port 3000`.

## Credits

Imagery: NASA Global Imagery Browse Services (GIBS), operated by NASA/GSFC/ESDIS.
Globe rendering: MapLibre GL JS.
