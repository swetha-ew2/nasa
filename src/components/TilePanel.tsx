import type { MapFile, RegionInfo, SeriesRecord, VariableInfo } from '../types';
import { fmt, fmtP, fmtSigned, unitExplain } from '../lib/data';

interface Props {
  tileId: string;
  mapData: MapFile | null;
  variable: VariableInfo;
  regions: RegionInfo[];
  hotspots: SeriesRecord[];
  onOpenRegion: (id: string) => void;
  onOpenHotspot: (id: string) => void;
  onClose: () => void;
}

const fl = (v: number, p: string, q: string) => `${Math.abs(v)}°${v >= 0 ? p : q}`;

export default function TilePanel({ tileId, mapData, variable, regions, hotspots, onOpenRegion, onOpenHotspot, onClose }: Props) {
  const [la, lo] = tileId.split(',').map(Number);
  let slope: number | null = null;
  let p: number | null = null;
  let effect: number | null = null;
  let sig = false;
  if (mapData) {
    const i = mapData.lat.findIndex((x) => x === la);
    const j = mapData.lon.findIndex((x) => x === lo);
    if (i >= 0 && j >= 0) {
      const k = i * mapData.lon.length + j;
      slope = mapData.slope[k];
      p = mapData.p[k];
      effect = mapData.effect_size[k];
      sig = mapData.significant[k] === 1;
    }
  }
  const inRegions = regions.filter((r) => r.id !== 'global' && lo >= r.bbox[0] && lo <= r.bbox[2] && la >= r.bbox[1] && la <= r.bbox[3]);
  const inHotspot = hotspots.find((h) => h.cells?.some(([a, b]) => a === la && b === lo));
  const dir = (slope ?? 0) > 0 ? 'increasing' : 'decreasing';
  const tone = slope === null ? 'nodata' : sig ? ((slope ?? 0) > 0 ? 'up' : 'down') : 'none';

  return (
    <aside className="panel" aria-label="Tile details">
      <header className="panel__head">
        <div>
          <span className="eyebrow">Map tile</span>
          <h2>{fl(la, 'N', 'S')}, {fl(lo, 'E', 'W')}</h2>
          <p className="muted small">A 5° × 5° square, about 550 km on each side near the equator.</p>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close panel">✕</button>
      </header>

      <section className="defn" aria-label="Definition">
        <span className="eyebrow">{variable.name}</span>
        <p className="defn__text">{variable.definition}</p>
        <p className="defn__unit"><strong>Unit:</strong> {variable.units === 'index' ? '' : `${variable.units}, `}{unitExplain(variable.id, variable.units)}</p>
      </section>

      {!mapData && <p className="muted">Loading…</p>}
      {mapData && slope === null && (
        <div className="verdict verdict--nodata">
          <strong>No data here</strong>
          <p>This variable has no measurements for this tile.</p>
        </div>
      )}
      {slope !== null && (
        <>
          <div className={`verdict verdict--${tone}`}>
            <strong>{sig ? `Significant trend: ${dir}` : 'No significant trend'}</strong>
            <p>
              {fmtSigned(slope)} {variable.units} per decade (p = {fmtP(p)}).{' '}
              {sig
                ? 'This tile passes the strict test that accounts for checking all 2,592 tiles at once.'
                : 'The change is small compared with natural variation, or too uncertain on a single tile. That does not prove nothing is happening.'}
            </p>
          </div>
          <div className="stats">
            <div className="stat">
              <div className="stat__value">{fmtSigned(slope)}</div>
              <div className="stat__label">Change per decade</div>
              <div className="stat__hint">in {variable.units}</div>
            </div>
            <div className="stat">
              <div className="stat__value">{fmtP(p)}</div>
              <div className="stat__label">p-value</div>
              <div className="stat__hint">lower = stronger evidence</div>
            </div>
            <div className="stat">
              <div className="stat__value">{fmt(effect, 2)}</div>
              <div className="stat__label">Effect size</div>
              <div className="stat__hint">total change ÷ monthly noise</div>
            </div>
          </div>
        </>
      )}

      {(inRegions.length > 0 || inHotspot) && (
        <div className="belongs">
          <span className="eyebrow">This tile is part of</span>
          {inHotspot && (
            <button className="hs-item" onClick={() => onOpenHotspot(inHotspot.id)}>
              <span className={`hs-item__dir hs-item__dir--${inHotspot.direction === 'increasing' ? 'up' : 'down'}`}>
                {inHotspot.direction === 'increasing' ? '▲' : '▼'}
              </span>
              <span className="hs-item__name">Hotspot: {inHotspot.name}</span>
              <span className="hs-item__val">open →</span>
            </button>
          )}
          {inRegions.map((r) => (
            <button key={r.id} className="hs-item" onClick={() => onOpenRegion(r.id)}>
              <span className="hs-item__dir">●</span>
              <span className="hs-item__name">Region: {r.name}</span>
              <span className="hs-item__val">open →</span>
            </button>
          ))}
        </div>
      )}
      <p className="muted small">
        A single tile has no monthly chart. Open its region or hotspot to see the time series and trend line.
      </p>
    </aside>
  );
}
