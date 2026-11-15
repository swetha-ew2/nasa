import { useMemo, useState } from 'react';
import type { Interesting, Manifest, SeriesRecord } from '../types';
import { fmtSigned } from '../lib/data';

interface Props {
  manifest: Manifest;
  interesting: Interesting | null;
  variableId: string | null;
  hotspots: SeriesRecord[];
  onSelectHotspot: (id: string) => void;
  onSelectVariable: (id: string) => void;
  onGoTo: (variableId: string, regionId: string | null) => void;
  onOpenMethods: () => void;
}

export default function Catalog({ manifest, interesting, variableId, hotspots, onSelectHotspot, onSelectVariable, onGoTo, onOpenMethods }: Props) {
  const [tab, setTab] = useState<'variables' | 'signs'>('variables');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [showAll, setShowAll] = useState(false);
  const cats = useMemo(() => ['All', ...Array.from(new Set(manifest.variables.map((v) => v.category)))], [manifest]);
  const groups = useMemo(() => {
    const m = new Map<string, { region: string; name: string; ipcc: boolean; items: Interesting['items'] }>();
    interesting?.items.forEach((it) => {
      const ipcc = it.group === 'ipcc';
      const g = m.get(it.region) ?? { region: it.region, name: it.region === 'global' ? 'Worldwide' : it.region_name, ipcc, items: [] };
      g.items.push(it);
      m.set(it.region, g);
    });
    return Array.from(m.values()).sort((a, b) => b.items.length - a.items.length);
  }, [interesting]);

  const filtered = manifest.variables.filter((v) => {
    if (category !== 'All' && v.category !== category) return false;
    const q = query.trim().toLowerCase();
    return !q || v.name.toLowerCase().includes(q) || v.definition.toLowerCase().includes(q) || v.source.toLowerCase().includes(q);
  });

  return (
    <section className="catalog" aria-label="Variables and early signs">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'variables'} className={tab === 'variables' ? 'on' : ''} onClick={() => setTab('variables')}>
          Variables
        </button>
        <button role="tab" aria-selected={tab === 'signs'} className={tab === 'signs' ? 'on' : ''} onClick={() => setTab('signs')}>
          Early signs
          {interesting && <span className="count">{interesting.items.length}</span>}
        </button>
      </div>

      {tab === 'variables' && (
        <>
          <input className="search" type="search" placeholder="Search (e.g. rain, smoke, ice)…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="chips" role="group" aria-label="Filter by category">
            {cats.map((c) => (
              <button key={c} className={`chip ${category === c ? 'chip--on' : ''}`} onClick={() => setCategory(c)}>{c}</button>
            ))}
          </div>

          <div className="list-head">
            <span>Variable</span>
            <span title="Faint numbers are not statistically significant">Worldwide change per decade</span>
          </div>
          <ul className="cards">
            {filtered.map((v) => {
              const on = v.id === variableId;
              const s = v.global_slope_per_decade;
              return (
                <li key={v.id}>
                  <button className={`card ${on ? 'card--on' : ''}`} onClick={() => onSelectVariable(v.id)} aria-pressed={on}>
                    <span className={`dot dot--${v.category.replace(/\s+/g, '-').toLowerCase()}`} title={v.category} />
                    <span className="card__name">{v.name}</span>
                    {s !== null && (
                      <span
                        className={`card__val ${v.global_p !== null && v.global_p >= 0.05 ? 'card__val--ns' : ''}`}
                        title={`Worldwide: ${fmtSigned(s)} ${v.units} per decade${v.global_p !== null && v.global_p >= 0.05 ? ' (not statistically significant)' : ''}`}
                      >
                        <b>{s > 0 ? '▲' : '▼'} {fmtSigned(s)}</b>
                        <small>{v.units}/decade</small>
                      </span>
                    )}
                  </button>
                  {on && hotspots.length > 0 && (
                    <div className="hs-list">
                      <div className="eyebrow">Hotspots the data found</div>
                      {(showAll ? hotspots : hotspots.slice(0, 5)).map((h) => (
                        <button key={h.id} className="hs-item" onClick={() => onSelectHotspot(h.id)}>
                          <span className={`hs-item__dir hs-item__dir--${h.direction === 'increasing' ? 'up' : 'down'}`}>
                            {h.direction === 'increasing' ? '▲' : '▼'}
                          </span>
                          <span className="hs-item__name">{h.name}</span>
                          <span className="hs-item__val">{fmtSigned(h.slope_per_decade)} {v.units}/decade</span>
                        </button>
                      ))}
                      {hotspots.length > 5 && (
                        <button className="show-all" onClick={() => setShowAll(!showAll)}>
                          {showAll ? 'Show fewer' : `Show all ${hotspots.length}`}
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
            {filtered.length === 0 && <li className="muted small">No variables match.</li>}
          </ul>
        </>
      )}

      {tab === 'signs' && (
        <div className="watch">
          <p className="small muted">
            Changes that just missed the strict test but look consistent over time.{' '}
            <button className="link-btn" onClick={onOpenMethods}>Why?</button>
          </p>
          {[false, true].map((ipcc) => {
            const list = groups.filter((g) => g.ipcc === ipcc);
            if (!list.length) return null;
            return (
              <div key={String(ipcc)}>
                <div className="eyebrow watch__head">
                  {ipcc ? 'IPCC regions · just missed the strict test, same direction in both halves of the record' : 'Spotlight regions and worldwide'}
                </div>
                {list.map((g) => (
            <div className="story" key={g.region}>
              <div className="story__title">
                {g.name} <span className="muted">· {g.items.length}</span>
              </div>
              <div className="chips">
                {g.items.map((it) => (
                  <button key={it.var} className="chip" onClick={() => onGoTo(it.var, g.region)}>
                    <span className={it.slope_per_decade > 0 ? 'up' : 'down'}>{it.slope_per_decade > 0 ? '▲' : '▼'}</span> {it.var_name}
                  </button>
                ))}
              </div>
            </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
