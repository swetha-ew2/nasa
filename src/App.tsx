import { useMemo, useState } from 'react';
import Globe from './components/Globe';
import Catalog from './components/Catalog';
import RegionPanel from './components/RegionPanel';
import { REGIONS, REGIONS_BY_ID } from './data/regions';

export default function App() {
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  /** Variable chosen in the catalog; highlights matching pins on the globe. */
  const [catalogVariableId, setCatalogVariableId] = useState<string | null>(null);
  /** Variable currently shown in the region panel. */
  const [panelVariableId, setPanelVariableId] = useState<string | null>(null);
  const [showImagery, setShowImagery] = useState(true);
  const [autoRotate, setAutoRotate] = useState(true);

  const region = selectedRegionId ? REGIONS_BY_ID[selectedRegionId] : null;

  const highlightIds = useMemo(() => {
    if (!catalogVariableId) return null;
    return new Set(REGIONS.filter((r) => r.variableIds.includes(catalogVariableId)).map((r) => r.id));
  }, [catalogVariableId]);

  function handleSelectRegion(id: string | null) {
    setSelectedRegionId(id);
    if (id) {
      setAutoRotate(false);
      const r = REGIONS_BY_ID[id];
      setPanelVariableId(
        catalogVariableId && r.variableIds.includes(catalogVariableId)
          ? catalogVariableId
          : r.variableIds[0],
      );
    }
  }

  function handleSelectVariable(id: string | null) {
    setCatalogVariableId(id);
    // If a region is open, jump its panel to the chosen variable.
    if (id && selectedRegionId) setPanelVariableId(id);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__logo" aria-hidden>
            ◐
          </span>
          <div>
            <h1>Earth System Trend Detective</h1>
            <p className="muted small">Prototype · all values shown are placeholders</p>
          </div>
        </div>
        <div className="toolbar">
          <label className="toggle">
            <input
              type="checkbox"
              checked={showImagery}
              onChange={(e) => setShowImagery(e.target.checked)}
            />
            Satellite imagery
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={autoRotate}
              onChange={(e) => setAutoRotate(e.target.checked)}
            />
            Auto-rotate
          </label>
        </div>
      </header>

      <main className="layout">
        <Catalog selectedVariableId={catalogVariableId} onSelectVariable={handleSelectVariable} />

        <div className="stage">
          <Globe
            regions={REGIONS}
            selectedRegionId={selectedRegionId}
            highlightRegionIds={highlightIds}
            showImagery={showImagery}
            autoRotate={autoRotate}
            onSelectRegion={handleSelectRegion}
            onUserInteract={() => setAutoRotate(false)}
          />

          <div className="legend" aria-label="Pin colour legend">
            <div className="legend__title">Pin colour (placeholder)</div>
            <div><i className="swatch swatch--increasing" /> Increasing</div>
            <div><i className="swatch swatch--decreasing" /> Decreasing</div>
            <div><i className="swatch swatch--none" /> No significant trend</div>
            <div><i className="swatch swatch--pending" /> Not analysed yet</div>
          </div>

          <div className="hint">Drag to rotate · scroll to zoom · click a pin</div>

          {region && panelVariableId && (
            <RegionPanel
              region={region}
              variableId={panelVariableId}
              onChangeVariable={setPanelVariableId}
              onClose={() => setSelectedRegionId(null)}
            />
          )}
        </div>
      </main>
    </div>
  );
}
