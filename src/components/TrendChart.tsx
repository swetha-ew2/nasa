import { useMemo } from 'react';
import { makePlaceholderSeries, olsLine } from '../lib/placeholder';

interface Props {
  seed: string;
  title: string;
  units: string;
}

const W = 340;
const H = 170;
const M = { l: 10, r: 10, t: 22, b: 24 };

/**
 * Placeholder time-series chart (plain SVG, no chart library).
 * Replace with Plotly / ECharts once real data is wired in.
 */
export default function TrendChart({ seed, title, units }: Props) {
  const { pathD, trendD, xTicks } = useMemo(() => {
    const s = makePlaceholderSeries(seed);
    const t0 = s.t[0];
    const t1 = s.t[s.t.length - 1];
    const yMin = Math.min(...s.y);
    const yMax = Math.max(...s.y);
    const pad = (yMax - yMin) * 0.1;

    const x = (t: number) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);
    const y = (v: number) =>
      H - M.b - ((v - (yMin - pad)) / (yMax - yMin + 2 * pad)) * (H - M.t - M.b);

    const pathD = s.y.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(s.t[i]).toFixed(1)},${y(v).toFixed(1)}`).join(' ');

    const { a, b } = olsLine(s.t, s.y);
    const trendD = `M${x(t0).toFixed(1)},${y(a + b * t0).toFixed(1)} L${x(t1).toFixed(1)},${y(a + b * t1).toFixed(1)}`;

    const xTicks = [
      { label: String(Math.floor(t0)), px: x(t0), anchor: 'start' as const },
      { label: String(Math.round((t0 + t1) / 2)), px: x((t0 + t1) / 2), anchor: 'middle' as const },
      { label: String(Math.floor(t1)), px: x(t1), anchor: 'end' as const },
    ];
    return { pathD, trendD, xTicks };
  }, [seed]);

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Placeholder time series of ${title}`}>
        <text x={M.l} y={13} className="chart__title">
          {title} ({units})
        </text>
        <line x1={M.l} x2={W - M.r} y1={H - M.b} y2={H - M.b} className="chart__axis" />
        <path d={pathD} className="chart__line" />
        <path d={trendD} className="chart__trend" />
        {xTicks.map((t) => (
          <text key={t.label} x={t.px} y={H - 8} textAnchor={t.anchor} className="chart__tick">
            {t.label}
          </text>
        ))}
        <text x={W / 2} y={H / 2} textAnchor="middle" className="chart__watermark">
          PLACEHOLDER DATA
        </text>
      </svg>
      <figcaption>
        Synthetic values for layout only. Dashed line is illustrative, not a statistical result.
      </figcaption>
    </figure>
  );
}
