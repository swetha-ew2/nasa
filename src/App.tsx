import { useEffect, useMemo, useRef, useState } from 'react';
import Globe, { type PinState } from './components/Globe';
import Catalog from './components/Catalog';
import DetailPanel from './components/DetailPanel';
import TilePanel from './components/TilePanel';
import Legend from './components/Legend';
import About from './components/About';
import Welcome from './components/Welcome';
import Tour, { TourAsk } from './components/Tour';
import type { Example } from './lib/examples';
import { analyseTiles, boxId, loadTileSeries, parseBoxId, tilesInBox } from './lib/custom';
import { TOUR_STEPS } from './components/Tour';
import { loadInteresting, loadIpccGeo, loadIpccTiles, loadManifest, loadMap, loadSeries } from './lib/data';
import type { Interesting, Manifest, MapFile, SeriesFile, SeriesRecord, Target } from './types';

const TOUR_STEPS_NEED_DEMO = TOUR_STEPS.flatMap((st, i) => (st.demo ? [i] : []));

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [interesting, setInteresting] = useState<Interesting | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [variableId, setVariableId] = useState<string | null>(null);
  const [mapData, setMapData] = useState<MapFile | null>(null);
  const [series, setSeries] = useState<SeriesFile | null>(null);
  const [target, setTarget] = useState<Target | null>(null);

  const [showHotspots, setShowHotspots] = useState(true);
  const [showIpcc, setShowIpcc] = useState(true);
  const [ipccGeo, setIpccGeo] = useState<GeoJSON.FeatureCollection | null>(null);
  const [ipccTiles, setIpccTiles] = useState<Record<string, string> | null>(null);
  const [showImagery, setShowImagery] = useState(true);
  const [autoRotate, setAutoRotate] = useState(true);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [started, setStarted] = useState(false); // false = intro: just the globe and the welcome popup
  // ask = offer the site guide, tour = the guide, home/examples = the question-flow screens
  const [phase, setPhase] = useState<'ask' | 'tour' | 'home' | 'examples' | null>('ask');
  const [tourStep, setTourStep] = useState(0);
  const tourBefore = useRef<{ started: boolean; hadVariable: boolean } | null>(null);
  const [guide, setGuide] = useState<Example | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [customRec, setCustomRec] = useState<SeriesRecord | null>(null);

  useEffect(() => {
    loadManifest().then(setManifest).catch((e) => setError(String(e.message ?? e)));
    loadInteresting().then(setInteresting).catch(() => setInteresting(null));
    loadIpccGeo().then(setIpccGeo).catch(() => setIpccGeo(null));
    loadIpccTiles().then(setIpccTiles).catch(() => setIpccTiles(null));
  }, []);

  // load the map and the series of the chosen variable together, so they never get out of step
  useEffect(() => {
    if (!variableId) return;
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

  // an area the user drew: computed in the browser from the per-tile series of the chosen variable
  const customKey = target?.kind === 'custom' ? target.id : null;
  useEffect(() => {
    setCustomRec(null);
    if (!customKey || !variableId || !manifest) return;
    const v = manifest.variables.find((x) => x.id === variableId);
    if (!v) return;
    let cancelled = false;
    loadTileSeries(v.id)
      .then((ts) => {
        if (cancelled) return;
        const box = parseBoxId(customKey);
        const r = analyseTiles(ts, tilesInBox(ts, box));
        setCustomRec({ ...r, bbox: box });
      })
      .catch((e) => !cancelled && setError(String(e.message ?? e)));
    return () => {
      cancelled = true;
    };
  }, [customKey, variableId, manifest]);

  const variable = manifest?.variables.find((v) => v.id === variableId) ?? null; // null until the user picks one
  const seriesReady = series && series.var === variableId ? series : null;

  const ipccStates = useMemo(() => {
    const out: Record<string, PinState> = {};
    seriesReady?.ipcc?.forEach((r) => {
      out[r.id] =
        r.status !== 'ok' ? 'nodata' : r.significant_fdr ? ((r.slope_per_decade ?? 0) > 0 ? 'up' : 'down') : 'none';
    });
    return out;
  }, [seriesReady]);

  const rec: SeriesRecord | null = useMemo(() => {
    if (target?.kind === 'custom') return customRec;
    if (!target || !seriesReady) return null;
    const list = target.kind === 'hotspot' ? seriesReady.hotspots : target.id.startsWith('ar6:') ? seriesReady.ipcc ?? [] : seriesReady.regions; // regions = the globe
    return list.find((r) => r.id === target.id) ?? null;
  }, [target, seriesReady, customRec]);

  const ipccInfo = manifest && target?.kind === 'region' ? manifest.ipcc_regions?.find((r) => r.id === target.id) ?? null : null;

  function selectVariable(id: string) {
    setVariableId(id);
    setGuide(null);
    // hotspots belong to one variable; a selected region stays, otherwise show the global result on the right
    if (!target || target.kind === 'hotspot') {
      setTarget({ kind: 'region', id: 'global' });
      setAutoRotate(false);
    }
  }

  function select(t: Target | null) {
    setTarget(t);
    if (t) setAutoRotate(false);
  }

  function goTo(vid: string, regionId: string | null, ex: Example | null = null, hotspotId: string | null = null) {
    setGuide(ex);
    setVariableId(vid);
    setTarget(hotspotId ? { kind: 'hotspot', id: hotspotId } : regionId ? { kind: 'region', id: regionId } : null);
    setAutoRotate(false);
    setStarted(true);
    setPhase(null);
  }

  function startTour() {
    tourBefore.current = { started, hadVariable: !!variableId };
    setStarted(true);
    setTourStep(0);
    setPhase('tour');
  }

  function goToStep(i: number) {
    setTourStep(i);
    // the colour legend and detail panel only exist once a variable is chosen: show an example while touring
    if (TOUR_STEPS_NEED_DEMO.includes(i) && !variableId) {
      setVariableId('t2m');
      setTarget({ kind: 'region', id: 'global' });
      setAutoRotate(false);
    }
  }

  function endTour() {
    const before = tourBefore.current;
    if (before && !before.hadVariable) {
      setVariableId(null);
      setTarget(null);
      setMapData(null);
      setSeries(null);
      setAutoRotate(true);
    }
    if (before && !before.started) setStarted(false);
    tourBefore.current = null;
    setPhase('home');
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
  if (!manifest) return <div className="splash"><p className="muted">Loading the Earth…</p></div>;

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
          <button className="ghost-btn" onClick={startTour}>Tour</button>
          <button className="ghost-btn" onClick={() => setPhase('examples')}>Ask a question</button>
          <button className="ghost-btn" onClick={() => setAboutOpen(true)}>Methods &amp; data</button>
        </div>
      </header>

      <main className={`layout ${started ? '' : 'layout--intro'}`}>
        <Catalog
          manifest={manifest}
          interesting={interesting}
          variableId={variableId}
          hotspots={seriesReady?.hotspots ?? []}
          onSelectVariable={selectVariable}
          onGoTo={goTo}
          onSelectHotspot={(id) => select({ kind: 'hotspot', id })}
          onOpenMethods={() => setAboutOpen(true)}
        />

        <div className="stage">
          <Globe
            mapData={variable && mapData && mapData.var === variableId ? mapData : null}
            scheme={variable?.scheme ?? 'neutral'}
            units={variable?.units ?? ''}
            showNonSig
            showHotspots={showHotspots}
            drawMode={drawing}
            onDraw={(b) => {
              setDrawing(false);
              if (b) {
                setTarget({ kind: 'custom', id: boxId(b) });
                setAutoRotate(false);
              }
            }}
            showIpcc={showIpcc}
            ipccGeo={ipccGeo}
            ipccTiles={ipccTiles}
            ipccStates={ipccStates}
            hotspots={seriesReady?.hotspots ?? []}
            target={target}
            highlightCells={
              target?.kind === 'hotspot'
                ? rec?.cells ?? null
                : target?.kind === 'tile'
                  ? [target.id.split(',').map(Number) as [number, number]]
                  : target?.kind === 'custom'
                    ? customRec?.cells ?? null
                    : null
            }
            showImagery={showImagery}
            autoRotate={autoRotate}
            onSelect={select}
            onUserInteract={() => setAutoRotate(false)}
          />

          {started && variable && <Legend
            variable={variable}
            limit={mapData?.color_limit ?? variable.map_color_limit}
            showHotspots={showHotspots}
            onToggleHotspots={setShowHotspots}
            showIpcc={showIpcc}
            onToggleIpcc={setShowIpcc}
          />}

          {started && !guide && !drawing && (
            <div className="hint">
              {variable ? 'Drag to rotate · scroll to zoom · hover for values · click a tile or a region marker' : 'Drag to rotate · scroll to zoom · pick a variable on the left'}
            </div>
          )}

          {guide && (
            <div className="guide" role="note">
              <div>
                <span className="eyebrow">Your question</span>
                <strong>{guide.question}</strong>
                <span className="small muted">Showing {guide.variableName} · {guide.placeName}. The answer is in the panel on the right.</span>
              </div>
              <button className="icon-btn" onClick={() => setGuide(null)} aria-label="Dismiss">✕</button>
            </div>
          )}

          {drawing && (
            <div className="guide guide--draw" role="note">
              <div>
                <span className="eyebrow">Draw an area</span>
                <strong>Drag on the globe to draw a box</strong>
                <span className="small muted">The trend of all tiles inside is computed. Press Esc or Cancel to stop.</span>
              </div>
              <button className="ghost-btn" onClick={() => setDrawing(false)}>Cancel</button>
            </div>
          )}

          {started && variable && !drawing && (
            <button className="global-btn draw-btn" onClick={() => { setDrawing(true); setTarget(null); setAutoRotate(false); }}>
              ✎ Draw an area
            </button>
          )}

          {started && variable && (
            <button className="global-btn" onClick={() => select({ kind: 'region', id: 'global' })}>
              Global result
            </button>
          )}

          {target?.kind === 'tile' && variable && (
            <TilePanel
              tileId={target.id}
              mapData={mapData && mapData.var === variableId ? mapData : null}
              variable={variable}
              ipccRegions={manifest.ipcc_regions ?? []}
              ipccTiles={ipccTiles}
              hotspots={seriesReady?.hotspots ?? []}
              onOpenRegion={(id) => select({ kind: 'region', id })}
              onOpenHotspot={(id) => select({ kind: 'hotspot', id })}
              onClose={() => setTarget(null)}
            />
          )}
          {target && target.kind !== 'tile' && variable && (
            <DetailPanel
              target={target}
              rec={rec}
              ipcc={ipccInfo}
              variable={variable}
              variables={manifest.variables}
              onChangeVariable={selectVariable}
              onClose={() => setTarget(null)}
            />
          )}
        </div>
      </main>

      {phase === 'ask' && (
        <TourAsk
          onStart={startTour}
          onSkip={() => setPhase('home')}
        />
      )}
      {phase === 'tour' && <Tour step={tourStep} onStep={goToStep} onDone={endTour} />}
      {(phase === 'home' || phase === 'examples') && (
        <Welcome
          manifest={manifest}
          start={phase === 'examples' ? 'questions' : 'home'}
          onPick={(ex) => goTo(ex.variable, ex.region, ex, ex.hotspot ?? null)}
          onBrowse={() => {
            setStarted(true);
            setPhase(null);
          }}
        />
      )}
      {aboutOpen && <About manifest={manifest} onClose={() => setAboutOpen(false)} />}
    </div>
  );
}
