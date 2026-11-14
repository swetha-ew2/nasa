import { useMemo, useState } from 'react';
import type { Interesting, Manifest, SeriesRecord } from '../types';
import { fmtSigned } from '../lib/data';

interface Props {
  manifest: Manifest;
  interesting: Interesting | null;
  variableId: string;
  hotspots: SeriesRecord[];
  onSelectHotspot: (id: string) => void;
  onSelectVariable: (id: string) => void;
  onGoTo: (variableId: string, regionId: string | null) => void;
}

const EXAMPLES: { label: string; blurb: string; variable: string; region: string | null }[] = [
  { label: 'Is the planet warming?', blurb: 'Global air temperature, 2005–2024.', variable: 't2m', region: 'global' },
  { label: 'How fast is the sea rising?', blurb: 'Sea level from satellite altimeters.', variable: 'sea_level', region: 'global' },
  { label: 'Is the Mediterranean drying?', blurb: 'Soil moisture over the Mediterranean.', variable: 'soil_moist_10_40', region: 'med' },
  { label: 'Is the Sahel greening?', blurb: 'Vegetation over the Sahel.', variable: 'ndvi', region: 'sahel' },
];

export default function Catalog({ manifest, interesting, variableId, hotspots, onSelectHotspot, onSelectVariable, onGoTo }: Props) {
  const [tab, setTab] = useState<'variables' | 'watch'>('variables');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const cats = useMemo(() => ['All', ...Array.from(new Set(manifest.variables.map((v) => v.category)))], [manifest]);
  const nameOf = (id: string) => manifest.variables.find((v) => v.id === id)?.name ?? id;

  const filtered = manifest.variables.filter((v) => {
    if (category !== 'All' && v.category !== category) return false;
    const q = query.trim().toLowerCase();
    return !q || v.name.toLowerCase().includes(q) || v.definition.toLowerCase().includes(q) || v.source.toLowerCase().includes(q);
  });

  return (
    <section className="catalog" aria-label="Variables and findings">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'variables'} className={tab === 'variables' ? 'on' : ''} onClick={() => setTab('variables')}>
          Variables
        </button>
        <button role="tab" aria-selected={tab === 'watch'} className={tab === 'watch' ? 'on' : ''} onClick={() => setTab('watch')}>
          Worth watching
          {interesting && <span className="count">{interesting.items.length}</span>}
        </button>
      </div>

      {tab === 'variables' && (
        <>
          <div className="examples">
            <div className="eyebrow">Try an example</div>
            <div className="examples__row">
              {EXAMPLES.map((ex) => (
                <button key={ex.label} className="example" onClick={() => onGoTo(ex.variable, ex.region)} title={ex.blurb}>
                  {ex.label}
                </button>
              ))}
            </div>
          </div>

          <input className="search" type="search" placeholder="Search (e.g. rain, smoke, ice)…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="chips" role="group" aria-label="Filter by category">
            {cats.map((c) => (
              <button key={c} className={`chip ${category === c ? 'chip--on' : ''}`} onClick={() => setCategory(c)}>{c}</button>
            ))}
          </div>

          <ul className="cards">
            {filtered.map((v) => {
              const on = v.id === variableId;
              return (
                <li key={v.id}>
                  <button className={`card ${on ? 'card--on' : ''}`} onClick={() => onSelectVariable(v.id)} aria-pressed={on}>
                    <div className="card__top">
                      <span className="card__name">{v.name}</span>
                      <span className={`badge badge--${v.role === 'headline' ? 'headline' : 'data'}`} title={v.role === 'headline' ? 'Chosen by hand because it is a core indicator' : 'Chosen by the data-driven selection'}>
                        {v.role === 'headline' ? 'Headline' : 'Data-picked'}
                      </span>
                    </div>
                    <div className="card__meta">
                      <span className={`dot dot--${v.category.replace(/\s+/g, '-').toLowerCase()}`} />
                      {v.category} ·{' '}
                      {v.global_slope_per_decade !== null && (
                        <span>
                          global {fmtSigned(v.global_slope_per_decade)} {v.units}/decade
                        </span>
                      )}
                    </div>
                    {on && (
                      <div className="card__detail">
                        <p>{v.definition}</p>
                        <p>{v.finding}</p>
                        <p className="muted small">{v.source} · {v.record}</p>
                      </div>
                    )}
                  </button>
                  {on && hotspots.length > 0 && (
                    <div className="hs-list">
                      <div className="eyebrow">Where it is changing most (exploratory)</div>
                      {hotspots.slice(0, 6).map((h) => (
                        <button key={h.id} className="hs-item" onClick={() => onSelectHotspot(h.id)}>
                          <span className={`hs-item__dir hs-item__dir--${h.direction === 'increasing' ? 'up' : 'down'}`}>
                            {h.direction === 'increasing' ? '▲' : '▼'}
                          </span>
                          <span className="hs-item__name">{h.name}</span>
                          <span className="hs-item__val">{fmtSigned(h.slope_per_decade)} {v.units}/dec</span>
                        </button>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
            {filtered.length === 0 && <li className="muted small">No variables match.</li>}
          </ul>
        </>
      )}

      {tab === 'watch' && (
        <div className="watch">
          <p className="small">
            These changes look real but <strong>did not pass the strict test</strong> once we account for checking many regions at once
            (p between 0.05 and 0.10, or significant only before the correction). They are leads, not conclusions: a longer record or
            better data could settle them.
          </p>
          {interesting?.stories.map((s) => (
            <div className="story" key={s.region}>
              <div className="story__title">{s.region === 'global' ? 'Worldwide' : s.region_name}: {s.n_variables} variables</div>
              <p className="small">{s.text}</p>
              <div className="chips">
                {s.variables.map((vid) => (
                  <button key={vid} className="chip" onClick={() => onGoTo(vid, s.region)}>{nameOf(vid)}</button>
                ))}
              </div>
            </div>
          ))}
          <div className="eyebrow">All individual hints</div>
          <ul className="cards">
            {interesting?.items.map((it) => (
              <li key={`${it.var}:${it.region}`}>
                <button className="card" onClick={() => onGoTo(it.var, it.region)}>
                  <div className="card__top">
                    <span className="card__name">{it.var_name}</span>
                    <span className="badge badge--hint">p = {it.p.toFixed(3)}</span>
                  </div>
                  <div className="card__meta">
                    {it.region === 'global' ? 'Worldwide' : it.region_name} · {fmtSigned(it.slope_per_decade)} {it.units}/decade
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
