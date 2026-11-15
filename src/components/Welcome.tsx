import { useState } from 'react';
import { EXAMPLES, type Example } from '../lib/examples';

interface Props {
  start: 'home' | 'examples';
  onPick: (ex: Example) => void;
  onBrowse: () => void;
}

export default function Welcome({ start, onPick, onBrowse }: Props) {
  const [stage, setStage] = useState(start);

  return (
    <div className={`welcome welcome--${stage}`} role="dialog" aria-modal="true" aria-label="Choose what to explore">
      <div className="welcome__box">
        {stage === 'home' ? (
          <>
            <span className="eyebrow">Earth System Trend Detective</span>
            <h2>What is changing on Earth?</h2>
            <p className="muted">
              Explore 20 years of NASA satellite data: what changed, where, by how much, and whether the change is real.
            </p>
            <div className="welcome__choices">
              <button className="welcome__choice" onClick={() => setStage('examples')}>
                <strong>Try a guided example</strong>
                <span>Start from a question, such as &ldquo;Is the planet warming?&rdquo;</span>
              </button>
              <button className="welcome__choice" onClick={onBrowse}>
                <strong>Explore on my own</strong>
                <span>Browse all 20 variables and pick what interests you.</span>
              </button>
            </div>
          </>
        ) : (
          <>
            <button className="link-btn welcome__back" onClick={() => setStage('home')}>← Back</button>
            <h2>Pick a question</h2>
            <p className="muted">Each one opens a variable and a place, with the answer in the panel on the right.</p>
            <div className="welcome__list">
              {EXAMPLES.map((ex) => (
                <button key={ex.question} className="welcome__ex" onClick={() => onPick(ex)}>
                  <strong>{ex.question}</strong>
                  <span>{ex.about}</span>
                  <em>Shows: {ex.variableName} · {ex.placeName}</em>
                </button>
              ))}
            </div>
            <button className="welcome__browse" onClick={onBrowse}>Or explore on my own →</button>
          </>
        )}
      </div>
    </div>
  );
}
