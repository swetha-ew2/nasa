import type { VariableInfo } from '../types';
import { fmt, gradientCss } from '../lib/data';

interface Props {
  variable: VariableInfo;
  limit: number;
  showHotspots: boolean;
  onToggleHotspots: (v: boolean) => void;
  showPins: boolean;
  onTogglePins: (v: boolean) => void;
}

export default function Legend({ variable, limit, showHotspots, onToggleHotspots, showPins, onTogglePins }: Props) {
  return (
    <div className="legend" aria-label="Map legend">
      <div className="legend__title">{variable.name}</div>
      <div className="legend__sub">Change per decade, in {variable.units}</div>
      <div className="legend__bar" style={{ background: gradientCss(variable.scheme) }} />
      <div className="legend__scale">
        <span>{fmt(-limit, 2)}</span>
        <span>0</span>
        <span>+{fmt(limit, 2)}</span>
      </div>
      <label className="legend__check legend__check--two">
        <input type="checkbox" checked={showPins} onChange={(e) => onTogglePins(e.target.checked)} />
        <i className="lg lg--region" />
        <span><strong>Named regions</strong><br /><span className="muted">fixed areas we chose in advance</span></span>
      </label>
      <label className="legend__check legend__check--two">
        <input type="checkbox" checked={showHotspots} onChange={(e) => onToggleHotspots(e.target.checked)} />
        <i className="lg lg--hot">▲</i>
        <span><strong>Hotspots</strong><br /><span className="muted">areas the data flagged</span></span>
      </label>
    </div>
  );
}
