import { useMemo, useState } from 'react';
import { CATEGORIES, VARIABLES } from '../data/variables';
import { REGIONS } from '../data/regions';
import type { AnalysisStatus, Category } from '../types';

interface Props {
  selectedVariableId: string | null;
  onSelectVariable: (id: string | null) => void;
}

const STATUS_LABEL: Record<AnalysisStatus, string> = {
  verified: 'Verified',
  experimental: 'Experimental',
  catalog: 'Catalog only',
};

export default function Catalog({ selectedVariableId, onSelectVariable }: Props) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<Category | 'All'>('All');

  const regionCount = useMemo(() => {
    const counts: Record<string, number> = {};
    REGIONS.forEach((r) => r.variableIds.forEach((v) => (counts[v] = (counts[v] ?? 0) + 1)));
    return counts;
  }, []);

  const filtered = VARIABLES.filter((v) => {
    if (category !== 'All' && v.category !== category) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      v.name.toLowerCase().includes(q) ||
      v.definition.toLowerCase().includes(q) ||
      v.source.toLowerCase().includes(q)
    );
  });

  return (
    <section className="catalog" aria-label="Variable catalog">
      <h2>Variable catalog</h2>
      <p className="muted small">
        Pick a variable to see which regions on the globe it applies to.
      </p>

      <input
        className="search"
        type="search"
        placeholder="Search variables (e.g. rain, smoke, ice)…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <div className="chips" role="group" aria-label="Filter by category">
        {(['All', ...CATEGORIES] as const).map((c) => (
          <button
            key={c}
            className={`chip ${category === c ? 'chip--on' : ''}`}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <ul className="cards">
        {filtered.map((v) => {
          const on = v.id === selectedVariableId;
          return (
            <li key={v.id}>
              <button
                className={`card ${on ? 'card--on' : ''}`}
                onClick={() => onSelectVariable(on ? null : v.id)}
                aria-pressed={on}
              >
                <div className="card__top">
                  <span className="card__name">{v.name}</span>
                  <span className={`badge badge--${v.status}`}>{STATUS_LABEL[v.status]}</span>
                </div>
                <div className="card__meta">
                  <span className={`dot dot--${v.category.replace(' ', '-').toLowerCase()}`} />
                  {v.category} · {regionCount[v.id] ?? 0} regions
                </div>
                {on && (
                  <div className="card__detail">
                    <p>{v.definition}</p>
                    <p className="muted small">
                      {v.source} · {v.record} · {v.units}
                    </p>
                  </div>
                )}
              </button>
            </li>
          );
        })}
        {filtered.length === 0 && <li className="muted small">No variables match.</li>}
      </ul>
    </section>
  );
}
