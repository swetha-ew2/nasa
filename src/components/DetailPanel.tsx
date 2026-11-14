import { useState } from 'react';
import type { RegionInfo, SeriesRecord, Target, VariableInfo } from '../types';
import { fmt, fmtP, fmtSigned, testName } from '../lib/data';
import TrendChart from './TrendChart';

interface Props {
  target: Target;
  rec: SeriesRecord | null; // null while loading
  region: RegionInfo | null;
  variable: VariableInfo;
  variables: VariableInfo[];
  onChangeVariable: (id: string) => void;
  onClose: () => void;
}

type Tone = 'up' | 'down' | 'hint' | 'none' | 'nodata';

const pEq = (p: number | undefined) => (fmtP(p).startsWith('<') ? `p ${fmtP(p)}` : `p = ${fmtP(p)}`);

function verdict(rec: SeriesRecord, units: string, isHotspot: boolean): { tone: Tone; title: string; text: string } {
  if (rec.status !== 'ok') {
    return {
      tone: 'nodata',
      title: 'No data here',
      text:
        rec.status === 'no_data'
          ? 'This variable has no measurements for this place (for example a land-only variable over the ocean, or an ocean-only one over land).'
          : 'Too little of this box has data to compute a reliable trend.',
    };
  }
  const s = rec.slope_per_decade ?? 0;
  const [lo, hi] = rec.ci95 ?? [0, 0];
  const dir = s > 0 ? 'increasing' : 'decreasing';
  const total = `Over the 20-year record that adds up to roughly ${fmtSigned(s * 2)} ${units}.`;
  const stat = `${fmtSigned(s)} ${units} per decade (95% confidence interval ${fmtSigned(lo)} to ${fmtSigned(hi)}; ${pEq(rec.p)}).`;
  if (isHotspot) {
    return {
      tone: s > 0 ? 'up' : 'down',
      title: `Exploratory hotspot: ${dir}`,
      text:
        `${stat} ${total} This area was picked because its cells show a significant trend, so this p-value is optimistic. ` +
        'Treat it as a lead to investigate, not as proof.',
    };
  }
  if (rec.significant_fdr) {
    return {
      tone: s > 0 ? 'up' : 'down',
      title: `Significant trend: ${dir}`,
      text: `${stat} ${total}`,
    };
  }
  if ((rec.p ?? 1) < 0.1) {
    return {
      tone: 'hint',
      title: 'A hint, not significant',
      text:
        `${stat} The direction looks ${dir}, but the evidence is not strong enough once we account for testing many regions, ` +
        'so it could still be chance. A longer record might settle it.',
    };
  }
  return {
    tone: 'none',
    title: 'No significant trend',
    text:
      `${stat} The change is small compared with natural month-to-month and year-to-year variation. ` +
      'That does not prove nothing is happening: 20 years can hide a slow trend.',
  };
}

export default function DetailPanel({ target, rec, region, variable, variables, onChangeVariable, onClose }: Props) {
  const [mode, setMode] = useState<'anomaly' | 'actual'>('anomaly');
  const isHotspot = target.kind === 'hotspot';
  const isGlobal = target.kind === 'region' && target.id === 'global';
  const analysed = region ? region.analysed_variables : [];
  const options = isHotspot ? [variable] : variables.filter((v) => analysed.length === 0 || analysed.includes(v.id) || v.id === variable.id);
  const v = rec ? verdict(rec, variable.units, isHotspot) : null;
  const [w, s, e, n] = rec?.bbox ?? [0, 0, 0, 0];

  return (
    <aside className="panel" aria-label="Details">
      <header className="panel__head">
        <div>
          <span className="eyebrow">{isHotspot ? 'Hotspot' : isGlobal ? 'Whole Earth' : 'Region'}</span>
          <h2>{rec?.name ?? region?.name ?? '…'}</h2>
          {rec && !isGlobal && (
            <p className="muted small">
              {s}° to {n}° lat, {w}° to {e}° lon
              {isHotspot && rec.n_cells ? ` · ${rec.n_cells} grid cells` : ''}
            </p>
          )}
          {rec && isGlobal && rec.cover !== null && rec.cover < 0.9 && (
            <p className="muted small">Average over the part of the globe that has data for this variable.</p>
          )}
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close panel">✕</button>
      </header>

      {region && region.blurb && !isHotspot && <p className="panel__blurb">{region.blurb}</p>}

      <label className="field">
        <span>Variable</span>
        <select value={variable.id} disabled={isHotspot} onChange={(e2) => onChangeVariable(e2.target.value)}>
          {options.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
      </label>

      <div className="var-info">
        <p>{variable.definition}</p>
        <p className="muted small">{variable.source}</p>
      </div>

      {!rec && <p className="muted">Loading…</p>}

      {rec && v && (
        <div className={`verdict verdict--${v.tone}`}>
          <strong>{v.title}</strong>
          <p>{v.text}</p>
        </div>
      )}

      {rec && rec.status === 'ok' && (
        <>
          <div className="seg" role="group" aria-label="Chart view">
            <button className={mode === 'anomaly' ? 'on' : ''} onClick={() => setMode('anomaly')}>Seasons removed</button>
            <button className={mode === 'actual' ? 'on' : ''} onClick={() => setMode('actual')}>Actual values</button>
          </div>
          <TrendChart rec={rec} units={variable.units} mode={mode} />
          <p className="muted small">
            {mode === 'anomaly'
              ? 'Each month minus the usual value for that calendar month, so the seasonal cycle does not hide the trend.'
              : 'Raw monthly averages, including the seasonal cycle. No trend line here.'}
          </p>

          <div className="stats">
            <div className="stat">
              <div className="stat__value">{fmtSigned(rec.slope_per_decade)}</div>
              <div className="stat__label">Rate of change</div>
              <div className="stat__hint">{variable.units} per decade (Sen slope)</div>
            </div>
            <div className="stat">
              <div className="stat__value stat__value--sm">{fmtSigned(rec.ci95?.[0])} to {fmtSigned(rec.ci95?.[1])}</div>
              <div className="stat__label">95% confidence interval</div>
              <div className="stat__hint">{rec.ci_excludes_zero ? 'does not include zero' : 'includes zero'}</div>
            </div>
            <div className="stat">
              <div className="stat__value">{fmtP(rec.p)}</div>
              <div className="stat__label">p-value</div>
              <div className="stat__hint">{testName(rec.test_used)}</div>
            </div>
            <div className="stat">
              <div className="stat__value">{fmt(rec.snr, 2)}</div>
              <div className="stat__label">Effect size</div>
              <div className="stat__hint">total change ÷ monthly noise · {rec.n_months} months</div>
            </div>
          </div>

          {isHotspot && rec.halves_slope_per_decade && (
            <p className={`note ${rec.consistent_in_both_halves ? 'note--ok' : ''}`}>
              {rec.consistent_in_both_halves ? 'Consistent: ' : 'Not consistent: '}
              the first half of the record gives {fmtSigned(rec.halves_slope_per_decade[0])} and the second half{' '}
              {fmtSigned(rec.halves_slope_per_decade[1])} {variable.units} per decade.
            </p>
          )}
        </>
      )}

      <details className="explain">
        <summary>How was this tested?</summary>
        <p>
          Seasons are removed, then the rate of change is the Sen slope (the median of all pairwise slopes, robust to
          outliers). Significance uses the Mann-Kendall test, adjusted because neighbouring months are not independent.
          For regions, p-values are corrected for testing many regions at once (false discovery rate, 5%).
        </p>
      </details>
    </aside>
  );
}
