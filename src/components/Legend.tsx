import type { VariableInfo } from '../types';
import { fmt, gradientCss } from '../lib/data';

interface Props {
  variable: VariableInfo;
  limit: number;
  showHotspots: boolean;
  onToggleHotspots: (v: boolean) => void;
  showIpcc: boolean;
  onToggleIpcc: (v: boolean) => void;
}

export default function Legend({ variable, limit, showHotspots, onToggleHotspots, showIpcc, onToggleIpcc }: Props) {
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
        <input type="checkbox" checked={showIpcc} onChange={(e) => onToggleIpcc(e.target.checked)} />
        <i className="lg lg--ipcc" />
        <span><strong>IPCC regions</strong><br /><span className="muted">58 standard regions covering the whole globe</span></span>
      </label>
      <label className="legend__check legend__check--two">
        <input type="checkbox" checked={showHotspots} onChange={(e) => onToggleHotspots(e.target.checked)} />
        <i className="lg lg--hot">▲</i>
        <span><strong>Hotspots</strong><br /><span className="muted">areas the data flagged</span></span>
      </label>
    </div>
  );
}
