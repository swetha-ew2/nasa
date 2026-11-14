import type { Region, TrendStatus } from '../types';
import { VARIABLES_BY_ID } from '../data/variables';
import TrendChart from './TrendChart';

interface Props {
  region: Region;
  variableId: string;
  onChangeVariable: (id: string) => void;
  onClose: () => void;
}

const TREND_LABEL: Record<TrendStatus, string> = {
  increasing: 'Increasing (placeholder)',
  decreasing: 'Decreasing (placeholder)',
  none: 'No significant trend (placeholder)',
  pending: 'Not analysed yet',
};

const STATS: { label: string; hint: string }[] = [
  { label: 'Rate of change', hint: 'units per decade' },
  { label: 'Mann-Kendall p-value', hint: 'is the trend significant?' },
  { label: '95% confidence interval', hint: 'range for the rate' },
  { label: 'Observations', hint: 'months in the record' },
];

export default function RegionPanel({ region, variableId, onChangeVariable, onClose }: Props) {
  const variable = VARIABLES_BY_ID[variableId];
  const options = region.variableIds.includes(variableId)
    ? region.variableIds
    : [...region.variableIds, variableId];
  const notSuggested = !region.variableIds.includes(variableId);
  const [w, s, e, n] = region.bbox;

  return (
    <aside className="panel" aria-label={`${region.name} details`}>
      <header className="panel__head">
        <div>
          <h2>{region.name}</h2>
          <p className="muted small">
            Box: {s}° to {n}° lat, {w}° to {e}° lon
          </p>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </header>

      <p className="panel__blurb">{region.blurb}</p>

      <span className={`badge badge--trend-${region.placeholderTrend}`}>
        {TREND_LABEL[region.placeholderTrend]}
      </span>

      <label className="field">
        <span>Variable</span>
        <select value={variableId} onChange={(e) => onChangeVariable(e.target.value)}>
          {options.map((id) => (
            <option key={id} value={id}>
              {VARIABLES_BY_ID[id].name}
            </option>
          ))}
        </select>
      </label>

      {notSuggested && (
        <p className="note">
          Not on the suggested list for this region. It would run as an experimental analysis.
        </p>
      )}

      <div className="var-info">
        <p>{variable.definition}</p>
        <p className="muted small">
          {variable.source} · {variable.record} · {variable.units}
        </p>
      </div>

      <TrendChart
        seed={`${region.id}:${variable.id}`}
        title={variable.name}
        units={variable.units}
      />

      <div className="stats">
        {STATS.map((st) => (
          <div className="stat" key={st.label}>
            <div className="stat__value">—</div>
            <div className="stat__label">{st.label}</div>
            <div className="stat__hint">{st.hint}</div>
          </div>
        ))}
      </div>

      <div className="verdict">
        <strong>Verdict:</strong> not computed yet. The trend test will run here.
      </div>

      <button className="primary-btn" disabled title="Analysis pipeline not connected yet">
        Run trend analysis
      </button>
    </aside>
  );
}
