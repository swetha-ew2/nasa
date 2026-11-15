// Trend statistics for an area the user draws. A TypeScript port of trends.py / regional.py (Mann-Kendall variant with the
// AR(1) variance inflation, Sen slope and its 95% CI), so a drawn area is tested exactly like the fixed regions.
// Drawn areas always use the Mann-Kendall test (the pipeline used it for 90% of regions).
import type { SeriesRecord } from '../types';

export interface TileSeries {
  months: number[];
  nlat: number;
  nlon: number;
  lat0: number;
  lon0: number;
  step: number;
  offset: Float32Array; // per tile
  scale: Float32Array;
  q: Int16Array; // tile-major: tile * T + month
}

const cache = new Map<string, Promise<TileSeries>>();

export function loadTileSeries(slug: string): Promise<TileSeries> {
  let p = cache.get(slug);
  if (!p) {
    const base = `${import.meta.env.BASE_URL}data/tiles/${slug}`;
    p = Promise.all([fetch(`${base}.json`).then((r) => r.json()), fetch(`${base}.bin`).then((r) => r.arrayBuffer())]).then(([meta, buf]) => {
      const n = meta.nlat * meta.nlon;
      return {
        ...meta,
        offset: new Float32Array(buf, 0, n),
        scale: new Float32Array(buf, n * 4, n),
        q: new Int16Array(buf, n * 8),
      } as TileSeries;
    });
    cache.set(slug, p);
    p.catch(() => cache.delete(slug));
  }
  return p;
}

// ---------------------------------------------------------------- small statistics helpers
function erfc(x: number) {
  // Numerical Recipes rational approximation of erfc (relative error < 1.2e-7, accurate in the tails)
  const z = Math.abs(x);
  const t = 1 / (1 + 0.5 * z);
  const y = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 +
    t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? y : 2 - y;
}
const Z975 = 1.959963984540054;

/** average ranks (ties share the mean rank), like scipy.stats.rankdata */
function rankdata(y: number[]): number[] {
  const idx = y.map((_, i) => i).sort((a, b) => y[a] - y[b]);
  const r = new Array<number>(y.length);
  let i = 0;
  while (i < idx.length) {
    let j = i;
    while (j + 1 < idx.length && y[idx[j + 1]] === y[idx[i]]) j++;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k]] = avg;
    i = j + 1;
  }
  return r;
}

const median = (a: number[]) => {
  const s = [...a].sort((x, y) => x - y);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
};

/** Mann-Kendall with the variance inflated for lag-1 autocorrelation of the detrended ranks, Sen slope + CI. t, y without NaNs. */
function mannKendall(t: number[], y: number[]) {
  const n = y.length;
  const N = (n * (n - 1)) / 2;
  const sl = new Float64Array(N);
  let k = 0;
  let S = 0;
  for (let i = 0; i < n - 1; i++) {
    for (let j = i + 1; j < n; j++) {
      const d = y[j] - y[i];
      sl[k++] = d / (t[j] - t[i]);
      S += Math.sign(d);
    }
  }
  const sorted = Float64Array.from(sl).sort();
  const slope = N % 2 ? sorted[(N - 1) / 2] : (sorted[N / 2 - 1] + sorted[N / 2]) / 2;
  // ties
  const counts = new Map<number, number>();
  y.forEach((v) => counts.set(v, (counts.get(v) ?? 0) + 1));
  let tieTerm = 0;
  counts.forEach((c) => (tieTerm += c * (c - 1) * (2 * c + 5)));
  const varS = (n * (n - 1) * (2 * n + 5) - tieTerm) / 18;
  const d = y.map((v, i) => v - slope * t[i]);
  const r = rankdata(d);
  const m = r.reduce((a, b) => a + b, 0) / n;
  const rc = r.map((v) => v - m);
  let denom = 0;
  let num = 0;
  for (let i = 0; i < n; i++) denom += rc[i] * rc[i];
  for (let i = 0; i < n - 1; i++) num += rc[i] * rc[i + 1];
  const rho = num / denom;
  const corr = Math.max(1, (1 + rho) / (1 - rho));
  const varC = varS * corr;
  const z = S === 0 ? 0 : (S - Math.sign(S)) / Math.sqrt(varC);
  const p = erfc(Math.abs(z) / Math.SQRT2); // two-sided p
  let lo = Math.floor((N - Z975 * Math.sqrt(varC)) / 2);
  let hi = Math.ceil((N + Z975 * Math.sqrt(varC)) / 2);
  lo = Math.max(lo, 0);
  hi = Math.min(hi, N - 1);
  return { slope, lo: sorted[lo], hi: sorted[hi], p };
}

/** deseasonalise: subtract each calendar month's mean (NaN-aware) */
function anomalies(x: number[], months: number[]): number[] {
  const sum = new Array(12).fill(0);
  const cnt = new Array(12).fill(0);
  x.forEach((v, i) => {
    if (Number.isFinite(v)) {
      const c = (months[i] % 100) - 1;
      sum[c] += v;
      cnt[c]++;
    }
  });
  return x.map((v, i) => {
    const c = (months[i] % 100) - 1;
    return v - sum[c] / cnt[c];
  });
}

const r4 = (x: number) => (Number.isFinite(x) ? Number(x.toPrecision(4)) : NaN);

/** statistics of one monthly series (an area mean), shaped like the pipeline's records */
export function seriesRecord(ser: number[], months: number[]): Partial<SeriesRecord> | null {
  const t = months.map((m) => Math.floor(m / 100) - Math.floor(months[0] / 100) + ((m % 100) - 1) / 12);
  const anom = anomalies(ser, months);
  const tt: number[] = [];
  const yy: number[] = [];
  anom.forEach((v, i) => {
    if (Number.isFinite(v)) {
      tt.push(t[i]);
      yy.push(v);
    }
  });
  if (yy.length / anom.length < 0.9) return null;
  const mk = mannKendall(tt, yy);
  const s = mk.slope;
  const icpt = median(anom.map((v, i) => v - s * t[i]).filter(Number.isFinite));
  const c0 = median(yy.map((w, j) => w - s * tt[j]));
  const resid = yy.map((v, i) => v - (c0 + s * tt[i]));
  const mean = resid.reduce((a, b) => a + b, 0) / resid.length;
  const sd = Math.sqrt(resid.reduce((a, b) => a + (b - mean) ** 2, 0) / (resid.length - 2));
  const p = Math.max(mk.p, 1e-16);
  return {
    status: 'ok',
    months,
    raw: ser.map((v) => (Number.isFinite(v) ? r4(v) : (null as unknown as number))),
    anomaly: anom.map((v) => (Number.isFinite(v) ? r4(v) : (null as unknown as number))),
    slope_per_decade: r4(s * 10),
    ci95: [r4(mk.lo * 10), r4(mk.hi * 10)],
    p_mk: r4(p),
    p: r4(p),
    test_used: 'mk',
    snr: sd > 0 ? r4((s * (tt[tt.length - 1] - tt[0])) / sd) : undefined,
    n_months: yy.length,
    sen_intercept: r4(icpt),
    ci_excludes_zero: mk.lo > 0 || mk.hi < 0,
  };
}

// ---------------------------------------------------------------- drawing a box
export type Box = [number, number, number, number]; // west, south, east, north (east may exceed 180 for a box over the dateline)

export const boxId = (b: Box) => b.map((x) => Number(x.toFixed(2))).join(',');
export const parseBoxId = (id: string): Box => id.split(',').map(Number) as Box;

const MIN_TILES = 3;
const MIN_COVER = 0.5;

/** indices of the tiles whose centre lies inside the box */
export function tilesInBox(ts: Pick<TileSeries, 'nlat' | 'nlon' | 'lat0' | 'lon0' | 'step'>, b: Box): number[] {
  const out: number[] = [];
  for (let i = 0; i < ts.nlat; i++) {
    const la = ts.lat0 + i * ts.step;
    if (la < b[1] || la > b[3]) continue;
    for (let j = 0; j < ts.nlon; j++) {
      const lo = ts.lon0 + j * ts.step;
      if ((lo >= b[0] && lo <= b[2]) || (lo + 360 >= b[0] && lo + 360 <= b[2])) out.push(i * ts.nlon + j);
    }
  }
  return out;
}

/** area-weighted (cos latitude) monthly mean of the given tiles, then the trend statistics */
export function analyseTiles(ts: TileSeries, tiles: number[]): SeriesRecord {
  const T = ts.months.length;
  const base: SeriesRecord = { id: 'custom', name: 'Your area', bbox: [0, 0, 0, 0], cover: null, status: 'no_data' };
  const sum = new Float64Array(T);
  const wsum = new Float64Array(T);
  let wAll = 0;
  let withData = 0;
  const cells: [number, number][] = [];
  tiles.forEach((k) => {
    const la = ts.lat0 + Math.floor(k / ts.nlon) * ts.step;
    const w = Math.cos((la * Math.PI) / 180);
    wAll += w;
    let valid = 0;
    for (let m = 0; m < T; m++) {
      const q = ts.q[k * T + m];
      if (q === -32768) continue;
      valid++;
      sum[m] += w * (ts.offset[k] + (q + 32500) * ts.scale[k]);
      wsum[m] += w;
    }
    if (valid / T > 0.9) {
      withData++;
      cells.push([la, ts.lon0 + (k % ts.nlon) * ts.step]);
    }
  });
  const ser = Array.from(sum, (s, m) => (wsum[m] > 0 ? s / wsum[m] : NaN));
  const cover = wAll > 0 ? median(Array.from(wsum, (x) => x / wAll)) : 0;
  const rec: SeriesRecord = { ...base, cover: r4(cover), n_tiles: tiles.length, n_tiles_data: withData, cells };
  if (withData < MIN_TILES || cover < MIN_COVER || ser.filter(Number.isFinite).length / T < 0.9) {
    rec.status = withData === 0 ? 'no_data' : 'insufficient_coverage';
    return rec;
  }
  const full = seriesRecord(ser, ts.months);
  if (!full) {
    rec.status = 'insufficient_coverage';
    return rec;
  }
  return { ...rec, ...full } as SeriesRecord;
}
