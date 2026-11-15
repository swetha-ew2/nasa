import type { Interesting, MapFile, Manifest, Scheme, SeriesFile } from '../types';

// ---------------------------------------------------------------- loading
const cache = new Map<string, Promise<unknown>>();

function getJson<T>(path: string): Promise<T> {
  let p = cache.get(path);
  if (!p) {
    p = fetch(`${import.meta.env.BASE_URL}data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`Could not load ${path} (${r.status})`);
      return r.json();
    });
    cache.set(path, p);
    p.catch(() => cache.delete(path));
  }
  return p as Promise<T>;
}

export const loadManifest = () => getJson<Manifest>('manifest.json');
export const loadMap = (id: string) => getJson<MapFile>(`maps/${id}.json`);
export const loadSeries = (id: string) => getJson<SeriesFile>(`series/${id}.json`);
export const loadInteresting = () => getJson<Interesting>('interesting.json');

// ---------------------------------------------------------------- colour scales
// Diverging, colour-blind-safe (ColorBrewer RdBu / BrBG / PRGn-like / PuOr), negative -> positive.
const STOPS: Record<Scheme, string[]> = {
  heat: ['#2166ac', '#67a9cf', '#d1e5f0', '#f7f7f7', '#fddbc7', '#ef8a62', '#b2182b'],
  water: ['#8c510a', '#d8b365', '#f6e8c3', '#f5f5f5', '#c7eae5', '#5ab4ac', '#01665e'],
  green: ['#8c510a', '#d8b365', '#f6e8c3', '#f5f5f5', '#d9f0d3', '#7fbf7b', '#1b7837'],
  neutral: ['#542788', '#998ec3', '#d8daeb', '#f7f7f7', '#fee0b6', '#f1a340', '#b35806'],
};

function rgb(hex: string): [number, number, number] {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

/** t in [-1, 1] (value / colour limit) -> hex colour on the scheme. */
export function colorAt(scheme: Scheme, t: number): string {
  const s = STOPS[scheme];
  const x = (Math.max(-1, Math.min(1, t)) + 1) / 2 * (s.length - 1);
  const i = Math.min(s.length - 2, Math.floor(x));
  const f = x - i;
  const a = rgb(s[i]);
  const b = rgb(s[i + 1]);
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

export function gradientCss(scheme: Scheme): string {
  return `linear-gradient(to right, ${STOPS[scheme].join(', ')})`;
}

export function endColors(scheme: Scheme): { neg: string; pos: string } {
  const s = STOPS[scheme];
  return { neg: s[1], pos: s[5] };
}

// ---------------------------------------------------------------- map cells -> GeoJSON
export function cellsGeoJSON(m: MapFile, scheme: Scheme, showNonSig: boolean): GeoJSON.FeatureCollection {
  const nx = m.lon.length;
  const features: GeoJSON.Feature[] = [];
  for (let i = 0; i < m.lat.length; i++) {
    for (let j = 0; j < nx; j++) {
      const k = i * nx + j;
      const v = m.slope[k];
      if (v === null) continue;
      const sig = m.significant[k] === 1;
      if (!sig && !showNonSig) continue;
      const t = Math.max(-1, Math.min(1, v / m.color_limit));
      const s = Math.min(1, Math.abs(t));
      const la0 = Math.max(-85, m.lat[i] - 2.5);
      const la1 = Math.min(85, m.lat[i] + 2.5);
      const lo0 = m.lon[j] - 2.5;
      const lo1 = m.lon[j] + 2.5;
      features.push({
        type: 'Feature',
        properties: {
          c: sig ? colorAt(scheme, t) : '#8da2c4',
          op: sig ? 0.55 + 0.4 * s : 0.1 + 0.08 * s,
          v,
          sig: sig ? 1 : 0,
          p: m.p[k],
          e: m.effect_size[k],
          la: m.lat[i],
          lo: m.lon[j],
        },
        geometry: { type: 'Polygon', coordinates: [[[lo0, la0], [lo1, la0], [lo1, la1], [lo0, la1], [lo0, la0]]] },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

export function cellsOutline(cells: [number, number][]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: cells.map(([la, lo]) => ({
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [lo - 2.5, Math.max(-85, la - 2.5)], [lo + 2.5, Math.max(-85, la - 2.5)],
          [lo + 2.5, Math.min(85, la + 2.5)], [lo - 2.5, Math.min(85, la + 2.5)],
          [lo - 2.5, Math.max(-85, la - 2.5)],
        ]],
      },
    })),
  };
}

// ---------------------------------------------------------------- formatting
export function fmt(x: number | null | undefined, digits = 3): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return '–';
  if (x === 0) return '0';
  const a = Math.abs(x);
  if (a >= 1e5 || a < 1e-3) return x.toExponential(2).replace('e+', '×10^').replace('e-', '×10^-');
  return Number(x.toPrecision(digits)).toString();
}

export function fmtSigned(x: number | null | undefined, digits = 3): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return '–';
  return (x > 0 ? '+' : '') + fmt(x, digits);
}

export function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined) return '–';
  if (p < 1e-15) return '< 1e-15';
  if (p < 0.001) return '< 0.001';
  return p.toPrecision(2);
}

export function decimalYear(yyyymm: number): number {
  return Math.floor(yyyymm / 100) + ((yyyymm % 100) - 1) / 12;
}

export function testName(t: 'ols' | 'mk' | undefined): string {
  return t === 'ols' ? 'OLS t-test' : 'Mann-Kendall test (adjusted for autocorrelation)';
}

/** plain-language meaning of a unit, so nobody has to guess what "kg/m²" or "index" is */
export function unitExplain(id: string, units: string): string {
  const byId: Record<string, string> = {
    ndvi: 'greenness index from 0 (bare ground) to 1 (dense green plants)',
    aod: 'haze index with no unit; higher means more dust, smoke or salt in the air',
    soil_wetness_top: 'fraction from 0 (dry) to 1 (saturated)',
    tws: 'millimetres of water spread over the area, counting soil, snow, groundwater and rivers',
    runoff: 'kilograms of water per square metre, about the same as millimetres of water',
  };
  if (byId[id]) return byId[id];
  const byUnit: Record<string, string> = {
    '°C': 'degrees Celsius',
    cm: 'centimetres',
    m: 'metres',
    'mm/day': 'millimetres of water per day',
    '% of area': 'percentage points of the area covered',
    'W/m²': 'watts per square metre, a measure of energy flow',
    'kg/m²': 'kilograms of water per square metre, about the same as millimetres of water',
    K: 'kelvin; a change of 1 K is the same as a change of 1 °C',
  };
  return byUnit[units] ?? units;
}
