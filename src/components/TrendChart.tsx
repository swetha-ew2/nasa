import { useMemo, useState } from 'react';
import type { SeriesRecord } from '../types';
import { decimalYear, fmt } from '../lib/data';

interface Props {
  rec: SeriesRecord;
  units: string;
  mode: 'anomaly' | 'actual';
}

const W = 360;
const H = 220;
const M = { l: 44, r: 10, t: 12, b: 26 };

function niceStep(range: number, ticks: number) {
  const raw = range / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const f = raw / mag;
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * mag;
}

/** Real time series: monthly values, 12-month mean, Sen trend line and the slope uncertainty fan. */
export default function TrendChart({ rec, units, mode }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const g = useMemo(() => {
    const months = rec.months ?? [];
    const t = months.map(decimalYear);
    const y = (mode === 'anomaly' ? rec.anomaly : rec.raw) ?? [];
    const sm = y.map((_, i) => {
      if (i < 11) return null;
      const w = y.slice(i - 11, i + 1).filter((v): v is number => v !== null);
      return w.length >= 9 ? w.reduce((a, b) => a + b, 0) / w.length : null;
    });
    const t0 = t[0];
    const t1 = t[t.length - 1];
    const slopeY = (rec.slope_per_decade ?? 0) / 10; // per year
    const trendAt = (tt: number) => slopeY * (tt - t0) + (rec.sen_intercept ?? 0);
    const showTrend = mode === 'anomaly' && rec.slope_per_decade !== undefined;
    const vals = y.filter((v): v is number => v !== null);
    const tl = showTrend ? [trendAt(t0), trendAt(t1)] : [];
    let lo = Math.min(...vals, ...tl);
    let hi = Math.max(...vals, ...tl);
    if (hi === lo) {
      hi += 1;
      lo -= 1;
    }
    const pad = (hi - lo) * 0.08;
    lo -= pad;
    hi += pad;
    const step = niceStep(hi - lo, 4);
    const yt: number[] = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) yt.push(Number(v.toFixed(10)));
    const X = (tt: number) => M.l + ((tt - t0) / (t1 - t0)) * (W - M.l - M.r);
    const Y = (v: number) => H - M.b - ((v - lo) / (hi - lo)) * (H - M.t - M.b);
    const path = (arr: (number | null)[]) => {
      let d = '';
      let pen = false;
      arr.forEach((v, i) => {
        if (v === null) {
          pen = false;
          return;
        }
        d += `${pen ? 'L' : 'M'}${X(t[i]).toFixed(1)},${Y(v).toFixed(1)} `;
        pen = true;
      });
      return d;
    };
    let fan = '';
    let trend = '';
    if (showTrend) {
      const tm = (t0 + t1) / 2;
      const ym = trendAt(tm);
      const loS = (rec.ci95?.[0] ?? slopeY * 10) / 10;
      const hiS = (rec.ci95?.[1] ?? slopeY * 10) / 10;
      fan = `M${X(t0)},${Y(ym + loS * (t0 - tm))} L${X(t1)},${Y(ym + loS * (t1 - tm))} L${X(t1)},${Y(ym + hiS * (t1 - tm))} L${X(t0)},${Y(ym + hiS * (t0 - tm))} Z`;
      trend = `M${X(t0)},${Y(trendAt(t0))} L${X(t1)},${Y(trendAt(t1))}`;
    }
    const xt: number[] = [];
    for (let yr = Math.ceil(t0); yr <= t1 + 0.9; yr += 5) xt.push(yr);
    return { t, y, sm, X, Y, path, fan, trend, yt, xt, line: path(y), smooth: path(sm) };
  }, [rec, mode]);

  const n = g.t.length;
  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const t0 = g.t[0];
    const t1 = g.t[n - 1];
    const tt = t0 + ((px - M.l) / (W - M.l - M.r)) * (t1 - t0);
    const i = Math.round((tt - t0) * 12);
    setHover(i >= 0 && i < n ? i : null);
  }
  const hv = hover !== null ? g.y[hover] : null;

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Monthly ${mode === 'anomaly' ? 'anomaly' : 'values'} of ${rec.name}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {g.yt.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={g.Y(v)} y2={g.Y(v)} className={v === 0 && mode === 'anomaly' ? 'chart__zero' : 'chart__grid'} />
            <text x={M.l - 5} y={g.Y(v) + 3} textAnchor="end" className="chart__tick">{fmt(v, 3)}</text>
          </g>
        ))}
        {g.xt.map((yr) => (
          <text key={yr} x={g.X(yr)} y={H - 8} textAnchor="middle" className="chart__tick">{yr}</text>
        ))}
        {g.fan && <path d={g.fan} className="chart__fan" />}
        <path d={g.line} className="chart__line" />
        <path d={g.smooth} className="chart__smooth" />
        {g.trend && <path d={g.trend} className="chart__trend" />}
        {hover !== null && hv !== null && hv !== undefined && (
          <g>
            <line x1={g.X(g.t[hover])} x2={g.X(g.t[hover])} y1={M.t} y2={H - M.b} className="chart__cursor" />
            <circle cx={g.X(g.t[hover])} cy={g.Y(hv)} r={3.2} className="chart__dot" />
          </g>
        )}
      </svg>
      <figcaption>
        {hover !== null && hv !== null && hv !== undefined ? (
          <>
            <strong>{String(rec.months![hover]).replace(/(\d{4})(\d{2})/, '$1-$2')}</strong>: {fmt(hv, 4)} {units}
          </>
        ) : (
          <>
            <span className="key key--line" /> monthly <span className="key key--smooth" /> 12-month average{' '}
            {mode === 'anomaly' && (
              <>
                <span className="key key--trend" /> trend <span className="key key--fan" /> 95% range of the rate
              </>
            )}
          </>
        )}
      </figcaption>
    </figure>
  );
}
