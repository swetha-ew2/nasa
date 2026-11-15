import { useMemo, useState } from 'react';
import type { Manifest } from '../types';
import type { Example } from '../lib/examples';
import { THEMES, type JourneyQuestion, type JourneyTheme } from '../lib/journey';

interface Props {
  manifest: Manifest;
  start: 'home' | 'questions';
  onPick: (ex: Example) => void;
  onBrowse: () => void;
}

type Stage = 'home' | 'theme' | 'question' | 'where';

export default function Welcome({ manifest, start, onPick, onBrowse }: Props) {
  const [stage, setStage] = useState<Stage>(start === 'questions' ? 'theme' : 'home');
  const [theme, setTheme] = useState<JourneyTheme | null>(null);
  const [question, setQuestion] = useState<JourneyQuestion | null>(null);
  const [regionId, setRegionId] = useState('');

  const variable = question ? manifest.variables.find((v) => v.id === question.variable) ?? null : null;

  // the hotspot where this variable changes most, relative to its colour scale
  const strongest = useMemo(() => {
    if (!variable) return null;
    const list = manifest.hotspots[variable.id] ?? [];
    const lim = variable.map_color_limit || 1;
    return [...list].sort((a, b) => Math.abs(b.slope_per_decade) / lim - Math.abs(a.slope_per_decade) / lim)[0] ?? null;
  }, [manifest, variable]);

  // ocean variables only make sense over ocean regions, land ones over land
  const regionOptions = useMemo(() => {
    if (!variable) return [];
    const kind = variable.category === 'Ocean' ? 'ocean' : variable.category === 'Land' || variable.category === 'Cryosphere' ? 'land' : null;
    const list = manifest.ipcc_regions.filter((r) => !kind || r.kind === kind);
    return list;
  }, [manifest, variable]);

  const finish = (place: { region: string | null; hotspot?: string | null; placeName: string }) => {
    if (!question || !variable) return;
    onPick({ question: question.q, about: question.about, variable: variable.id, variableName: variable.name, ...place });
  };

  const step = stage === 'theme' ? 1 : stage === 'question' ? 2 : 3;

  return (
    <div className={`welcome welcome--${stage === 'home' ? 'home' : 'examples'}`} role="dialog" aria-modal="true" aria-label="Choose what to explore">
      <div className="welcome__box">
        {stage === 'home' && (
          <>
            <span className="eyebrow">Earth System Trend Detective</span>
            <h2>What is changing on Earth?</h2>
            <p className="muted">
              Explore 20 years of NASA satellite data: what changed, where, by how much, and whether the change is real.
            </p>
            <div className="welcome__choices">
              <button className="welcome__choice" onClick={() => setStage('theme')}>
                <strong>Answer a few questions</strong>
                <span>Tell us what you are curious about and we will find the right data for you.</span>
              </button>
              <button className="welcome__choice" onClick={onBrowse}>
                <strong>Explore on my own</strong>
                <span>Browse all 20 variables and pick what interests you.</span>
              </button>
            </div>
          </>
        )}

        {stage !== 'home' && (
          <>
            <button
              className="link-btn welcome__back"
              onClick={() => setStage(stage === 'theme' ? 'home' : stage === 'question' ? 'theme' : 'question')}
            >
              ← Back
            </button>
            <span className="eyebrow">Question {step} of 3</span>
          </>
        )}

        {stage === 'theme' && (
          <>
            <h2>What are you curious about?</h2>
            <div className="welcome__grid">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  className="welcome__q"
                  onClick={() => {
                    setTheme(t);
                    setStage('question');
                  }}
                >
                  <strong>{t.label}</strong>
                  <span>{t.blurb}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {stage === 'question' && theme && (
          <>
            <h2>{theme.label}: which question?</h2>
            <div className="welcome__list">
              {theme.questions.map((q) => (
                <button
                  key={q.q}
                  className="welcome__ex"
                  onClick={() => {
                    setQuestion(q);
                    setRegionId('');
                    setStage('where');
                  }}
                >
                  <strong>{q.q}</strong>
                  <span>{q.about}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {stage === 'where' && question && variable && (
          <>
            <h2>Where do you want to look?</h2>
            <p className="muted small">{question.q}</p>
            <div className="welcome__list">
              <button className="welcome__ex" onClick={() => finish({ region: 'global', placeName: 'Whole Earth' })}>
                <strong>Worldwide</strong>
                <span>One number for the whole planet, plus the map.</span>
              </button>
              {strongest && (
                <button className="welcome__ex" onClick={() => finish({ region: null, hotspot: strongest.id, placeName: strongest.name })}>
                  <strong>Where is it changing most?</strong>
                  <span>Jump to the strongest hotspot for this variable: {strongest.name}.</span>
                </button>
              )}
              <label className="welcome__ex welcome__pick">
                <strong>A region I choose</strong>
                <select value={regionId} onChange={(e) => setRegionId(e.target.value)}>
                  <option value="">Pick a region…</option>
                  {regionOptions.map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
                <button
                  className="primary-btn"
                  disabled={!regionId}
                  onClick={() => finish({ region: regionId, placeName: regionOptions.find((r) => r.id === regionId)?.name ?? '' })}
                >
                  Show me
                </button>
              </label>
            </div>
          </>
        )}

        {stage !== 'home' && (
          <button className="welcome__browse" onClick={onBrowse}>Or explore on my own →</button>
        )}
      </div>
    </div>
  );
}
