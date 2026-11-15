import { useEffect, useLayoutEffect, useRef, useState } from 'react';

export interface TourStep {
  target: string; // CSS selector; several matches are highlighted together
  title: string;
  text: string;
  demo?: boolean; // needs a variable and the detail panel on screen
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: '.globe',
    title: 'The globe',
    text: 'This is Earth, with 20 years of NASA satellite data (2005–2024). Drag to rotate, scroll to zoom. Once you pick a variable, the globe is coloured by how fast it is changing.',
  },
  {
    target: '.catalog',
    title: 'Variables',
    text: 'Twenty things we can measure from space. The arrow and number show how much each changed per decade, worldwide: ▲ rising, ▼ falling. Faint numbers are not statistically significant. Click one to see it on the globe.',
  },
  {
    target: '.tabs',
    title: 'Early signs',
    text: 'Changes that just missed the strict statistical test but point the same way throughout the 20 years. They are leads worth a closer look, not conclusions.',
  },
  {
    target: '.legend',
    title: 'Colours',
    text: 'Each tile of the globe is coloured by its change per decade, using the scale here. Bright tiles show a statistically significant trend. Faded tiles show no clear trend. Hover a tile for its number.',
    demo: true,
  },
  {
    target: '.legend__check--two',
    title: 'Regions and hotspots',
    text: 'IPCC regions (yellow outlines and square markers) are 58 standard regions covering the whole globe; + or − marks a significant change. Spotlight regions (round pins, off by default) are 11 places where change is easy to see. Hotspots (▲▼) are groups of touching tiles that change the same way. Click a tile or marker for its numbers.',
    demo: true,
  },
  {
    target: '.panel',
    title: 'The detail panel',
    text: 'Opens when you click a region, hotspot or the whole globe. It gives the variable’s definition and unit, a plain-language verdict, the monthly chart with its trend line, and the key numbers.',
    demo: true,
  },
  {
    target: '.toolbar',
    title: 'Top bar',
    text: 'Turn satellite imagery or rotation off, replay this tour, open guided examples, or read how everything was calculated and where the data comes from.',
  },
];

interface Props {
  step: number;
  onStep: (i: number) => void;
  onDone: () => void; // finished or skipped
}

interface Box { left: number; top: number; width: number; height: number }

function measure(selector: string): Box | null {
  const els = Array.from(document.querySelectorAll(selector)) as HTMLElement[];
  if (!els.length) return null;
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  els.forEach((el) => {
    const x = el.getBoundingClientRect();
    if (x.width === 0 && x.height === 0) return;
    l = Math.min(l, x.left); t = Math.min(t, x.top); r = Math.max(r, x.right); b = Math.max(b, x.bottom);
  });
  if (!Number.isFinite(l)) return null;
  return { left: l, top: t, width: r - l, height: b - t };
}

const TIP_W = 330;

export default function Tour({ step, onStep, onDone }: Props) {
  const s = TOUR_STEPS[step];
  const [box, setBox] = useState<Box | null>(null);
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  const tipRef = useRef<HTMLDivElement>(null);
  const [tipH, setTipH] = useState(240); // real height of the tooltip, so it never runs off the bottom

  // layouts animate and panels appear after a step starts, so keep measuring while the tour is open
  useLayoutEffect(() => {
    const tick = () => {
      setBox(measure(s.target));
      setVp({ w: window.innerWidth, h: window.innerHeight });
      if (tipRef.current) setTipH(tipRef.current.offsetHeight);
    };
    tick();
    const id = window.setInterval(tick, 150);
    window.addEventListener('resize', tick);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('resize', tick);
    };
  }, [s.target]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDone();
      if (e.key === 'ArrowRight') onStep(Math.min(step + 1, TOUR_STEPS.length - 1));
      if (e.key === 'ArrowLeft') onStep(Math.max(step - 1, 0));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step, onStep, onDone]);

  const pad = 6;
  const last = step === TOUR_STEPS.length - 1;

  // tooltip position: beside the highlight when there is room, otherwise inside it or below it
  let tip: { left: number; top: number } = { left: vp.w / 2 - TIP_W / 2, top: vp.h / 2 - 90 };
  if (box) {
    const big = box.width > vp.w * 0.55 && box.height > vp.h * 0.4;
    if (big) tip = { left: box.left + box.width / 2 - TIP_W / 2, top: box.top + box.height - tipH - 20 };
    else if (box.left + box.width + TIP_W + 24 < vp.w) tip = { left: box.left + box.width + 16, top: box.top + 8 };
    else if (box.left - TIP_W - 24 > 0) tip = { left: box.left - TIP_W - 16, top: box.top + 8 };
    else tip = { left: box.left + box.width / 2 - TIP_W / 2, top: box.top + box.height + 14 };
  }
  tip.left = Math.max(10, Math.min(vp.w - TIP_W - 10, tip.left));
  tip.top = Math.max(10, Math.min(vp.h - tipH - 12, tip.top));

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label="Website guide">
      {box ? (
        <div
          className="tour__spot"
          style={{ left: box.left - pad, top: box.top - pad, width: box.width + pad * 2, height: box.height + pad * 2 }}
        />
      ) : (
        <div className="tour__shade" />
      )}
      <div className="tour__tip" ref={tipRef} style={{ left: tip.left, top: tip.top, width: TIP_W }}>
        <span className="eyebrow">Guide · {step + 1} of {TOUR_STEPS.length}</span>
        <strong>{s.title}</strong>
        <p>{s.text}</p>
        <div className="tour__row">
          <button className="link-btn tour__skip" onClick={onDone}>Skip</button>
          <span className="tour__spacer" />
          {step > 0 && <button className="ghost-btn" onClick={() => onStep(step - 1)}>Back</button>}
          <button className="primary-btn" onClick={() => (last ? onDone() : onStep(step + 1))}>{last ? 'Done' : 'Next'}</button>
        </div>
      </div>
    </div>
  );
}

/** the very first card: offers the guide, or lets people skip straight on */
export function TourAsk({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  return (
    <div className="welcome welcome--home" role="dialog" aria-modal="true" aria-label="Welcome">
      <div className="welcome__box">
        <span className="eyebrow">Earth System Trend Detective</span>
        <h2>Welcome</h2>
        <p className="muted">
          Explore 20 years of NASA satellite data: what changed on Earth, where, by how much, and whether the change is real.
          Want a quick look around first? It takes under a minute.
        </p>
        <div className="welcome__row">
          <button className="primary-btn primary-btn--lg" onClick={onStart}>Show me around</button>
          <button className="ghost-btn ghost-btn--lg" onClick={onSkip}>Skip</button>
        </div>
      </div>
    </div>
  );
}
