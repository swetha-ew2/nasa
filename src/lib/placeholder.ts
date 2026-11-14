// Deterministic fake time series so the chart looks stable between renders.
// REMOVE once real data comes from the analysis pipeline.

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface Series {
  /** decimal years, e.g. 2003.0833 */
  t: number[];
  y: number[];
}

export function makePlaceholderSeries(seed: string, startYear = 2003, years = 22): Series {
  const rand = mulberry32(hashString(seed));
  const n = years * 12;
  const slope = (rand() - 0.5) * 0.02; // arbitrary drift per month
  const phase = rand() * Math.PI * 2;
  const amp = 0.8 + rand() * 0.8;
  const t: number[] = [];
  const y: number[] = [];
  for (let i = 0; i < n; i++) {
    t.push(startYear + i / 12);
    const season = amp * Math.sin((2 * Math.PI * i) / 12 + phase);
    const noise = (rand() - 0.5) * 0.9;
    y.push(season + slope * i + noise);
  }
  return { t, y };
}

/** Plain least-squares line, only used to draw an illustrative dashed line. */
export function olsLine(t: number[], y: number[]): { a: number; b: number } {
  const n = t.length;
  const mt = t.reduce((s, v) => s + v, 0) / n;
  const my = y.reduce((s, v) => s + v, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (t[i] - mt) * (y[i] - my);
    den += (t[i] - mt) ** 2;
  }
  const b = den === 0 ? 0 : num / den;
  return { a: my - b * mt, b };
}
