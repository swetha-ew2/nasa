import { useEffect, useMemo, useState } from 'react';
import Globe, { type PinState } from './components/Globe';
import Catalog from './components/Catalog';
import DetailPanel from './components/DetailPanel';
import Legend from './components/Legend';
import About from './components/About';
import { loadInteresting, loadManifest, loadMap, loadSeries } from './lib/data';
import type { Interesting, Manifest, MapFile, SeriesFile, SeriesRecord, Target } from './types';

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [interesting, setInteresting] = useState<Interesting | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [variableId, setVariableId] = useState('t2m');
  const [mapData, setMapData] = useState<MapFile | null>(null);
  const [series, setSeries] = useState<SeriesFile | null>(null);
  const [target, setTarget] = useState<Target | null>(null);

  const [showNonSig, setShowNonSig] = useState(true);
  const [showHotspots, setShowHotspots] = useState(true);
  const [showPins, setShowPins] = useState(true);
  const [showImagery, setShowImagery] = useState(true);
  const [autoRotate, setAutoRotate] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);

  useEffect(() => {
    loadManifest().then(setManifest).catch((e) => setError(String(e.message ?? e)));
    loadInteresting().then(setInteresting).catch(() => setInteresting(null));
  }, []);

  // load the map and the series of the chosen variable together, so they never get out of step
  useEffect(() => {
    let cancelled = false;
    Promise.all([loadMap(variableId), loadSeries(variableId)])
      .then(([m, s]) => {
        if (cancelled) return;
        setMapData(m);
        setSeries(s);
      })
      .catch((e) => !cancelled && setError(String(e.message ?? e)));
    return () => {
      cancelled = true;
    };
  }, [variableId]);

  const variable = manifest?.variables.find((v) => v.id === variableId) ?? null;
  const seriesReady = series && series.var === variableId ? series : null;

  const pinStates = useMemo(() => {
    const out: Record<string, PinState> = {};
    seriesReady?.regions.forEach((r) => {
      out[r.id] =
        r.status !== 'ok' ? 'nodata' : r.significant_fdr ? ((r.slope_per_decade ?? 0) > 0 ? 'up' : 'down') : 'none';
    });
    return out;
  }, [seriesReady]);

  const rec: SeriesRecord | null = useMemo(() => {
    if (!target || !seriesReady) return null;
    const list = target.kind === 'hotspot' ? seriesReady.hotspots : seriesReady.regions;
    return list.find((r) => r.id === target.id) ?? null;
  }, [target, seriesReady]);

  const region = manifest && target?.kind === 'region' ? manifest.regions.find((r) => r.id === target.id) ?? null : null;

  function selectVariable(id: string) {
    setVariableId(id);
    // hotspots belong to one variable; regions stay selected
    if (target?.kind === 'hotspot') setTarget(null);
  }

  function select(t: Target | null) {
    setTarget(t);
    if (t) setAutoRotate(false);
  }

  function goTo(vid: string, regionId: string | null) {
    setVariableId(vid);
    setTarget(regionId ? { kind: 'region', id: regionId } : null);
    setAutoRotate(false);
  }

  if (error) {
    return (
      <div className="splash">
        <h1>Could not load the data</h1>
        <p className="muted">{error}</p>
        <p className="muted small">Run <code>python export_frontend.py</code> to create public/data, then reload.</p>
      </div>
    );
  }
  if (!manifest || !variable) return <div className="splash"><p className="muted">Loading the Earth…</p></div>;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__logo" aria-hidden>◐</span>
          <div>
            <h1>{manifest.title}</h1>
            <p className="muted small">What is changing, where, how much, and is it significant? · NASA data, {manifest.window}</p>
          </div>
        </div>
        <div className="toolbar">
          <label className="toggle">
            <input type="checkbox" checked={showImagery} onChange={(e) => setShowImagery(e.target.checked)} />
            Satellite imagery
          </label>
          <label className="toggle">
            <input type="checkbox" checked={autoRotate} onChange={(e) => setAutoRotate(e.target.checked)} />
            Auto-rotate
          </label>
          <button className="ghost-btn" onClick={() => setAboutOpen(true)}>Methods &amp; data</button>
        </div>
      </header>

      <main className="layout">
        <Catalog
          manifest={manifest}
          interesting={interesting}
          variableId={variableId}
          hotspots={seriesReady?.hotspots ?? []}
          onSelectVariable={selectVariable}
          onGoTo={goTo}
          onSelectHotspot={(id) => select({ kind: 'hotspot', id })}
        />

        <div className="stage">
          <Globe
            regions={manifest.regions}
            pinStates={pinStates}
            mapData={mapData && mapData.var === variableId ? mapData : null}
            scheme={variable.scheme}
            units={variable.units}
            showNonSig={showNonSig}
            showHotspots={showHotspots}
            showPins={showPins}
            hotspots={seriesReady?.hotspots ?? []}
            target={target}
            highlightCells={target?.kind === 'hotspot' ? rec?.cells ?? null : null}
            showImagery={showImagery}
            autoRotate={autoRotate}
            onSelect={select}
            onUserInteract={() => setAutoRotate(false)}
          />

          <Legend
            variable={variable}
            limit={mapData?.color_limit ?? variable.map_color_limit}
            showNonSig={showNonSig}
            onToggleNonSig={setShowNonSig}
            showHotspots={showHotspots}
            onToggleHotspots={setShowHotspots}
            showPins={showPins}
            onTogglePins={setShowPins}
          />

          <div className="hint">Drag to rotate · scroll to zoom · hover for values · click a pin or ▲▼ hotspot</div>

          <button className="global-btn" onClick={() => select({ kind: 'region', id: 'global' })}>
            Global result for this variable
          </button>

          {target && (
            <DetailPanel
              target={target}
              rec={rec}
              region={region}
              variable={variable}
              variables={manifest.variables}
              onChangeVariable={selectVariable}
              onClose={() => setTarget(null)}
            />
          )}
        </div>
      </main>

      {aboutOpen && <About manifest={manifest} onClose={() => setAboutOpen(false)} />}
    </div>
  );
}
