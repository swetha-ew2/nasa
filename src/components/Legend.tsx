import type { VariableInfo } from '../types';
import { fmt, gradientCss } from '../lib/data';

interface Props {
  variable: VariableInfo;
  limit: number;
  showNonSig: boolean;
  onToggleNonSig: (v: boolean) => void;
  showHotspots: boolean;
  onToggleHotspots: (v: boolean) => void;
  showPins: boolean;
  onTogglePins: (v: boolean) => void;
}

export default function Legend({ variable, limit, showNonSig, onToggleNonSig, showHotspots, onToggleHotspots, showPins, onTogglePins }: Props) {
  return (
    <div className="legend" aria-label="Map legend">
      <div className="legend__title">{variable.name}</div>
      <div className="legend__sub">Trend per decade ({variable.units})</div>
      <div className="legend__bar" style={{ background: gradientCss(variable.scheme) }} />
      <div className="legend__scale">
        <span>{fmt(-limit, 2)}</span>
        <span>0</span>
        <span>+{fmt(limit, 2)}</span>
      </div>
      <div className="legend__row"><i className="legend__faded" /> faded = no significant trend</div>
      <label className="legend__check">
        <input type="checkbox" checked={showNonSig} onChange={(e) => onToggleNonSig(e.target.checked)} /> show faded cells
      </label>
      <label className="legend__check">
        <input type="checkbox" checked={showHotspots} onChange={(e) => onToggleHotspots(e.target.checked)} /> where it changes <span className="muted">▲▼ exploratory</span>
      </label>
      <label className="legend__check">
        <input type="checkbox" checked={showPins} onChange={(e) => onTogglePins(e.target.checked)} /> reference regions <span className="muted">fixed list</span>
      </label>
    </div>
  );
}
