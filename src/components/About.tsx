import type { Manifest } from '../types';

interface Props {
  manifest: Manifest;
  onClose: () => void;
}

const LABELS: Record<string, string> = {
  anomalies: 'Removing seasons',
  rate: 'Rate of change',
  tests: 'Is the trend real?',
  multiple_testing: 'Checking many places at once',
  effect_size: 'How big is it?',
};

export default function About({ manifest, onClose }: Props) {
  const sources = Array.from(new Set(manifest.variables.map((v) => v.source)));
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Methods and data" onClick={onClose}>
      <div className="modal__box" onClick={(e) => e.stopPropagation()}>
        <header className="panel__head">
          <h2>Methods, caveats and data</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <p className="small">
          {manifest.window}, {manifest.grid} grid. Every number was computed in advance from NASA data; nothing on this page is
          simulated.
        </p>

        <h3>How we test for a trend</h3>
        <dl>
          {Object.entries(manifest.methods).map(([k, t]) => (
            <div key={k}>
              <dt>{LABELS[k] ?? k}</dt>
              <dd>{t}</dd>
            </div>
          ))}
        </dl>

        <h3>Regions and hotspots</h3>
        <p className="small">
          <strong>IPCC regions</strong> are the 58 standard reference regions of the IPCC AR6 report (land and ocean), which together
          cover the whole globe. They are fixed before looking at the data, so their tests are fair. <strong>Hotspots</strong> are
          different: they are found from the data, per variable, so they are exploratory.
        </p>
        <p className="small">
          The map tiles are always the same 5° squares. A region&rsquo;s value is the average of the tiles whose centre lies inside
          it, so a tile on a border is counted once. Regions with fewer than 3 tiles carrying data are not tested, and the regions
          are corrected for multiple testing together.
        </p>

        <h3>Drawing your own area</h3>
        <p className="small">
          With a variable chosen, <strong>Draw an area</strong> lets you drag a box on the globe. Your browser averages the tiles whose
          centre is inside the box (weighted by area) and tests the trend with the same Mann-Kendall method used for the regions.
          Because you chose the box after looking at the map, the p-value is optimistic and nothing is corrected for testing many areas:
          treat it as exploratory. A box needs at least 3 tiles with data.
        </p>

        <h3>Early signs</h3>
        <p className="small">
          The <strong>Early signs</strong> tab lists changes that just missed the strict test. One rule applies to every region: the
          change passes a looser 10% correction for testing many regions (but not the strict 5% one), its 95% confidence interval
          excludes zero, and it points the same way in both the first and the second half of the record.
        </p>
        <p className="small">
          They are leads, not conclusions: a longer record or better data could settle them. Twenty years is short, and with about a
          thousand tests a few promising results are expected by chance.
        </p>

        <h3>Honest caveats</h3>
        <ul>
          {manifest.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <p className="small muted">{manifest.not_available}</p>

        <h3>NASA data and resources used</h3>
        <ul>
          {sources.map((s) => (
            <li key={s}>{s}</li>
          ))}
          <li>NASA GIBS (Blue Marble imagery for the globe background)</li>
          <li>NASA Earthdata Search / CMR and OPeNDAP, used to find and subset the data</li>
        </ul>
      </div>
    </div>
  );
}
