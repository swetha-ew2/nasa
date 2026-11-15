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

        <h3>Early signs</h3>
        <p className="small">
          The <strong>Early signs</strong> tab lists changes that look real but did not pass the strict test once we account for
          checking many regions at once (p between 0.05 and 0.10, or significant only before the correction). They are leads, not
          conclusions: a longer record or better data could settle them.
        </p>
        <p className="small">
          No single one passes on its own, but several pointing the same way in one region is worth a closer look. Twenty years is
          short, and with this many tests a few p-values below 0.05 are expected by chance.
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
