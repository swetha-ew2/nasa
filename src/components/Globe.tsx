import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapFile, Scheme, SeriesRecord, Target } from '../types';
import { cellsGeoJSON, cellsOutline, endColors, fmt, fmtP } from '../lib/data';

// NASA GIBS "Blue Marble" static imagery (no date needed, no login needed).
const GIBS_BLUE_MARBLE =
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg';

const IMAGERY_LAYER = 'gibs-blue-marble';
const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  projection: { type: 'globe' },
  sources: {
    [IMAGERY_LAYER]: { type: 'raster', tiles: [GIBS_BLUE_MARBLE], tileSize: 256, maxzoom: 8, attribution: 'NASA GIBS' },
  },
  layers: [
    { id: 'ocean', type: 'background', paint: { 'background-color': '#0b2a4a' } },
    { id: IMAGERY_LAYER, type: 'raster', source: IMAGERY_LAYER, paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.75 } },
  ],
};

/** angular distance (degrees) between two lng/lat points */
function angleDeg(lng1: number, lat1: number, lng2: number, lat2: number) {
  const r = Math.PI / 180;
  const c = Math.sin(lat1 * r) * Math.sin(lat2 * r) + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.cos((lng1 - lng2) * r);
  return Math.acos(Math.max(-1, Math.min(1, c))) / r;
}

/** is a screen point actually on the globe? Off the globe MapLibre snaps the pointer to the nearest edge, which made
 *  hover read-outs and clicks pick up the tile or region closest to the pointer. A point on the globe projects back to itself. */
function onGlobe(map: maplibregl.Map, pt: { x: number; y: number }) {
  const q = map.project(map.unproject([pt.x, pt.y]));
  return Math.hypot(q.x - pt.x, q.y - pt.y) < 3;
}

/** MapLibre draws the globe larger by 1 / cos(latitude of its centre) at the same zoom number, so a view centred near a pole looks
 *  massively zoomed in. These convert between the zoom number and the "equator-equivalent" zoom that we design views in. */
const bboxPoly = (b: [number, number, number, number]): number[][] => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]];


// ---- free (trackball) rotation: dragging can carry the globe over the poles ----
type V3 = [number, number, number];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const add = (a: V3, b: V3, kb: number, ka = 1): V3 => [a[0] * ka + b[0] * kb, a[1] * ka + b[1] * kb, a[2] * ka + b[2] * kb];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: V3): V3 => {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
};
const MAX_LAT = 85;
/** time the last trackball drag ended; MapLibre still fires a click after it (its jumpTo resets the click guard) */
let lastDragEnd = 0;
/** draw mode: the trackball and clicks stand aside while the user drags out a box */
let drawModeOn = false;

/** the camera's centre direction and "up" direction, from the map's centre and bearing */
function basisOf(lngDeg: number, latDeg: number, bearingDeg: number): { c: V3; up: V3 } {
  const r = Math.PI / 180;
  const lam = lngDeg * r, phi = latDeg * r, b = bearingDeg * r;
  const c: V3 = [Math.cos(phi) * Math.cos(lam), Math.cos(phi) * Math.sin(lam), Math.sin(phi)];
  const east: V3 = [-Math.sin(lam), Math.cos(lam), 0];
  const north: V3 = [-Math.sin(phi) * Math.cos(lam), -Math.sin(phi) * Math.sin(lam), Math.cos(phi)];
  return { c, up: add(north, east, Math.sin(b), Math.cos(b)) };
}

/** centre and bearing from a camera basis */
function viewOf(c: V3, up: V3) {
  const phi = Math.asin(Math.max(-1, Math.min(1, c[2])));
  const lam = Math.atan2(c[1], c[0]);
  const east: V3 = [-Math.sin(lam), Math.cos(lam), 0];
  const north: V3 = [-Math.sin(phi) * Math.cos(lam), -Math.sin(phi) * Math.sin(lam), Math.cos(phi)];
  const d = 180 / Math.PI;
  return { lng: lam * d, lat: phi * d, bearing: Math.atan2(dot(up, east), dot(up, north)) * d };
}

/** drag the globe like a trackball. Returns a cleanup function. */
function enableTrackball(map: maplibregl.Map, onStart: () => void) {
  const el = map.getCanvasContainer();
  map.dragPan.disable(); // replaced by the trackball below
  let id: number | null = null;
  let last = { x: 0, y: 0 };
  let moved = false;
  let orient: { c: V3; up: V3 } | null = null;
  let applied: { lng: number; lat: number; bearing: number } | null = null;

  const down = (e: PointerEvent) => {
    if (drawModeOn) return;
    if (id !== null) { id = null; return; } // a second finger: leave it to pinch-zoom
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if ((e.target as HTMLElement).closest('.pin, .hs, .maplibregl-ctrl')) return;
    id = e.pointerId;
    last = { x: e.clientX, y: e.clientY };
    moved = false;
  };
  const move = (e: PointerEvent) => {
    if (id !== e.pointerId) return;
    const dx = e.clientX - last.x, dy = e.clientY - last.y;
    if (!moved && Math.hypot(dx, dy) < 3) return;
    if (!moved) onStart();
    moved = true;
    last = { x: e.clientX, y: e.clientY };
    // keep our own exact orientation between moves (the map's centre is clamped near the poles), and
    // only re-read it from the map when something else (a fly-to, the compass, the reset button) moved the camera
    const ctr = map.getCenter();
    const angDiff = (a: number, b: number) => Math.abs(((a - b + 540) % 360) - 180);
    const ap = applied;
    if (!ap || angDiff(ctr.lng, ap.lng) > 1e-4 || Math.abs(ctr.lat - ap.lat) > 1e-4 || angDiff(map.getBearing(), ap.bearing) > 1e-4) {
      orient = basisOf(ctr.lng, ctr.lat, map.getBearing());
    }
    let { c, up } = orient!;
    const right = norm(cross(up, c));
    const R = (512 * Math.pow(2, map.getZoom())) / (2 * Math.PI);
    const tx = -dx / R, ty = dy / R; // the point that was left of / above the centre comes to the centre
    c = norm(add(c, right, Math.sin(tx), Math.cos(tx)));
    up = norm(add(up, c, -dot(up, c))); // keep `up` perpendicular to the new centre
    const up1 = up;
    const c2 = norm(add(c, up1, Math.sin(ty), Math.cos(ty)));
    up = norm(add(up1, c, -Math.sin(ty), Math.cos(ty)));
    c = c2;
    up = norm(add(up, c, -dot(up, c)));
    orient = { c, up };
    const v = viewOf(c, up);
    const lat = Math.max(-MAX_LAT, Math.min(MAX_LAT, v.lat));
    map.jumpTo({ center: [v.lng, lat], bearing: v.bearing });
    const now = map.getCenter();
    applied = { lng: now.lng, lat: now.lat, bearing: map.getBearing() };
  };
  const up = (e: PointerEvent) => {
    if (id === e.pointerId) {
      if (moved) lastDragEnd = performance.now();
      id = null;
    }
  };
  el.addEventListener('pointerdown', down);
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', up);
  return () => {
    el.removeEventListener('pointerdown', down);
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', up);
  };
}

export type PinState = 'up' | 'down' | 'none' | 'nodata';

interface Props {
  mapData: MapFile | null;
  scheme: Scheme;
  units: string;
  showNonSig: boolean;
  showHotspots: boolean;
  drawMode: boolean;
  onDraw: (box: [number, number, number, number] | null) => void; // null = cancelled
  showIpcc: boolean;
  ipccGeo: GeoJSON.FeatureCollection | null;
  ipccStates: Record<string, PinState>;
  ipccTiles: Record<string, string> | null; // tile "lat,lon" -> IPCC region id
  hotspots: SeriesRecord[];
  target: Target | null;
  highlightCells: [number, number][] | null;
  showImagery: boolean;
  autoRotate: boolean;
  onSelect: (t: Target | null) => void;
  onUserInteract: () => void;
}

function spanOf(b: [number, number, number, number]) {
  return Math.max(b[2] - b[0], (b[3] - b[1]) * 1.4);
}
function zoomFor(spanDeg: number) {
  // keep enough of the globe in view that it can still be dragged around comfortably
  return Math.max(1.4, Math.min(3.3, 3.0 - Math.log2(Math.max(spanDeg, 5) / 20) * 0.85));
}

export default function Globe(p: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ipccEls = useRef<Map<string, HTMLElement>>(new Map());
  const hotspotMarkers = useRef<maplibregl.Marker[]>([]);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  /** DOM marker -> [lng, lat]; used to hide markers on the far side of the globe */
  const markerPos = useRef<Map<HTMLElement, [number, number]>>(new Map());
  const spinRef = useRef(false);
  const homeZoom = useRef(2);
  const hadTarget = useRef(false);
  const [ready, setReady] = useState(false);

  const cb = useRef({ onSelect: p.onSelect, onUserInteract: p.onUserInteract, units: p.units, showIpcc: p.showIpcc, ipccTiles: p.ipccTiles, ipccGeo: p.ipccGeo, onDraw: p.onDraw });
  cb.current = { onSelect: p.onSelect, onUserInteract: p.onUserInteract, units: p.units, showIpcc: p.showIpcc, ipccTiles: p.ipccTiles, ipccGeo: p.ipccGeo, onDraw: p.onDraw };

  // ---- create the map once ----
  useEffect(() => {
    if (!containerRef.current) return;
    // size the first view so the globe fills about 70% of the smaller side of its container
    const box = containerRef.current;
    const startZoom = Math.max(1, Math.min(2.4, Math.log2((0.72 * Math.min(box.clientWidth, box.clientHeight || 600)) / 131)));
    homeZoom.current = startZoom;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: [10, 25],
      zoom: startZoom,
      minZoom: 0.8,
      maxZoom: 8,
      attributionControl: false,
    });
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __map: maplibregl.Map }).__map = map;
    map.addControl(
      new maplibregl.AttributionControl({ compact: true, customAttribution: 'Imagery: NASA GIBS / ESDIS' }),
      'bottom-right',
    );
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');

    map.on('style.load', () => {
      map.setProjection({ type: 'globe' });
      try {
        map.setSky({
          'sky-color': '#0a1f44',
          'sky-horizon-blend': 0.5,
          'horizon-color': '#2a6fc9',
          'horizon-fog-blend': 0.5,
          'fog-color': '#0a1f44',
          'fog-ground-blend': 0.5,
          'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
        });
      } catch (err) {
        console.warn('Atmosphere not applied:', err);
      }

      map.addSource('cells', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({
        id: 'cells-fill',
        type: 'fill',
        source: 'cells',
        paint: { 'fill-color': ['get', 'c'], 'fill-opacity': ['get', 'op'], 'fill-antialias': false },
      });
      // dims everything outside the selected region, so its tiles read as one group
      map.addSource('region-mask', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({ id: 'region-mask-fill', type: 'fill', source: 'region-mask', paint: { 'fill-color': '#02060e', 'fill-opacity': 0.55 } });
      // IPCC AR6 reference regions: exact outlines, optional (off until switched on)
      map.addSource('ipcc', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({ id: 'ipcc-fill', type: 'fill', source: 'ipcc', layout: { visibility: 'none' }, paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.01 } });
      map.addLayer({
        id: 'ipcc-line', type: 'line', source: 'ipcc', layout: { visibility: 'none' },
        paint: { 'line-color': '#ffd479', 'line-width': 1.1, 'line-opacity': 0.8 },
      });
      map.addSource('hotspot-cells', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({
        id: 'hotspot-cells-line',
        type: 'line',
        source: 'hotspot-cells',
        paint: { 'line-color': '#ffffff', 'line-width': 1.6, 'line-opacity': 0.95 },
      });
      map.addSource('region-outline', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({
        id: 'region-outline-fill',
        type: 'fill',
        source: 'region-outline',
        paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.05 },
      });
      map.addLayer({
        id: 'region-outline-line',
        type: 'line',
        source: 'region-outline',
        paint: { 'line-color': '#ffffff', 'line-width': 2, 'line-dasharray': [2, 1] },
      });

      // the box being drawn
      map.addSource('draw-box', { type: 'geojson', data: EMPTY_FC });
      map.addLayer({ id: 'draw-box-fill', type: 'fill', source: 'draw-box', paint: { 'fill-color': '#5ad1ff', 'fill-opacity': 0.18 } });
      map.addLayer({ id: 'draw-box-line', type: 'line', source: 'draw-box', paint: { 'line-color': '#5ad1ff', 'line-width': 2.5 } });

      // hover read-out for cells: what is changing here, and by how much
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'cell-popup', offset: 10 });
      popupRef.current = popup;
      map.on('mousemove', 'cells-fill', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        if (!onGlobe(map, e.point)) {
          popup.remove();
          map.getCanvas().style.cursor = '';
          return;
        }
        const pr = f.properties as { v: number; sig: number; p: number | null };
        const f0 = f.properties as { la?: number; lo?: number };
        const ipccId = cb.current.showIpcc && cb.current.ipccTiles ? cb.current.ipccTiles[`${f0.la},${f0.lo}`] : undefined;
        const ipccName = ipccId
          ? (cb.current.ipccGeo?.features.find((x) => (x.properties as { id: string }).id === ipccId)?.properties as { name: string } | undefined)?.name
          : undefined;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${pr.v > 0 ? '+' : ''}${fmt(Number(pr.v))}</strong> ${cb.current.units} per decade<br>` +
              (Number(pr.sig) === 1
                ? '<span class="pop-sig">significant trend</span>'
                : '<span class="pop-ns">not significant</span>') +
              (pr.p !== null && pr.p !== undefined ? ` · p = ${fmtP(Number(pr.p))}` : '') +
              (ipccName ? `<br><span class="pop-reg">IPCC region: <b>${ipccName}</b></span>` : '') +
              '<br><span class="pop-hint">Click for details</span>',
          )
          .addTo(map);
        map.getCanvas().style.cursor = 'crosshair';
      });
      map.on('mouseleave', 'cells-fill', () => {
        popup.remove();
        map.getCanvas().style.cursor = '';
      });
      setReady(true);
    });

    const updateVisibility = () => {
      const c = map.getCenter();
      markerPos.current.forEach(([lng, lat], el) => {
        el.style.visibility = angleDeg(c.lng, c.lat, lng, lat) > 74 ? 'hidden' : 'visible';
      });
    };
    map.on('move', updateVisibility);
    map.on('zoom', updateVisibility);
    (map as unknown as { _updateMarkerVisibility: () => void })._updateMarkerVisibility = updateVisibility;

    // clicking a tile opens that tile; clicking empty space clears the selection
    map.on('click', (e) => {
      if (drawModeOn || performance.now() - lastDragEnd < 400) return; // end of a drag / drawing, not a click
      const off = !onGlobe(map, e.point); // empty space around the globe
      const hit = off ? undefined : map.queryRenderedFeatures(e.point, { layers: ['cells-fill'] })[0];
      if (hit) {
        const { la, lo } = hit.properties as { la: number; lo: number };
        cb.current.onSelect({ kind: 'tile', id: `${la},${lo}` });
      } else {
        const reg = cb.current.showIpcc && !off ? map.queryRenderedFeatures(e.point, { layers: ['ipcc-fill'] })[0] : undefined;
        cb.current.onSelect(reg ? { kind: 'region', id: (reg.properties as { id: string }).id } : null);
      }
    });
    const stopSpin = () => cb.current.onUserInteract();
    const stopTrackball = enableTrackball(map, stopSpin);
    map.on('mousedown', stopSpin);
    map.on('touchstart', stopSpin);
    map.on('wheel', stopSpin);
    map.on('moveend', () => {
      if (!spinRef.current) return;
      const c = map.getCenter();
      c.lng -= 3;
      map.easeTo({ center: c, duration: 1000, easing: (t) => t });
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(containerRef.current);
    return () => {
      stopTrackball();
      ro.disconnect();
      spinRef.current = false;
      hotspotMarkers.current = [];
      markerPos.current.clear();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- draw mode: drag out a box; rotation and clicks are switched off meanwhile ----
  useEffect(() => {
    const map = mapRef.current;
    const host = containerRef.current;
    if (!map || !ready || !host) return;
    drawModeOn = p.drawMode;
    host.classList.toggle('globe--drawing', p.drawMode);
    const preview = map.getSource('draw-box') as maplibregl.GeoJSONSource | undefined;
    preview?.setData(EMPTY_FC);
    if (!p.drawMode) return;
    const el = map.getCanvasContainer();
    el.style.touchAction = 'none';
    let start: { x: number; y: number; id: number } | null = null;
    const toLL = (x: number, y: number) => {
      const r = el.getBoundingClientRect();
      if (!onGlobe(map, { x: x - r.left, y: y - r.top })) return null;
      const ll = map.unproject([x - r.left, y - r.top]);
      const c = map.getCenter();
      return angleDeg(c.lng, c.lat, ll.lng, ll.lat) > 80 ? null : ll; // beyond the visible globe
    };
    const boxOf = (x1: number, y1: number, x2: number, y2: number): [number, number, number, number] | null => {
      const a = toLL(x1, y1);
      const b = toLL(x2, y2);
      if (!a || !b) return null;
      let w = Math.min(a.lng, b.lng);
      let e = Math.max(a.lng, b.lng);
      if (e - w > 180) { const t = w; w = e; e = t + 360; } // the short way round: a box across the dateline
      return [w, Math.max(-90, Math.min(a.lat, b.lat)), e, Math.min(90, Math.max(a.lat, b.lat))];
    };
    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if ((e.target as HTMLElement).closest('.maplibregl-ctrl')) return;
      start = { x: e.clientX, y: e.clientY, id: e.pointerId };
      try { el.setPointerCapture(e.pointerId); } catch { /* not needed */ }
      e.preventDefault();
    };
    const move = (e: PointerEvent) => {
      if (!start || start.id !== e.pointerId) return;
      const b = boxOf(start.x, start.y, e.clientX, e.clientY);
      preview?.setData(b ? { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [bboxPoly(b)] } } : EMPTY_FC);
    };
    const up = (e: PointerEvent) => {
      if (!start || start.id !== e.pointerId) return;
      const s0 = start;
      start = null;
      preview?.setData(EMPTY_FC);
      if (Math.hypot(e.clientX - s0.x, e.clientY - s0.y) < 10) return; // a click, not a drag: keep waiting
      const b = boxOf(s0.x, s0.y, e.clientX, e.clientY);
      if (!b) return;
      lastDragEnd = performance.now();
      cb.current.onDraw(b);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cb.current.onDraw(null);
    };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    window.addEventListener('keydown', key);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      window.removeEventListener('keydown', key);
      el.style.touchAction = '';
      drawModeOn = false;
      host.classList.remove('globe--drawing');
    };
  }, [p.drawMode, ready]);

  // ---- IPCC region markers: one at the centre of each region, so every region can be clicked ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !p.showIpcc || !p.ipccGeo) return;
    const markers: maplibregl.Marker[] = [];
    p.ipccGeo.features.forEach((f) => {
      const pr = f.properties as { id: string; name: string; center: [number, number] };
      if (!pr.center) return;
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'pin pin--ipcc pin--nodata';
      el.setAttribute('aria-label', `IPCC region: ${pr.name}`);
      const dot = document.createElement('span');
      dot.className = 'pin__dot';
      const label = document.createElement('span');
      label.className = 'pin__label';
      label.textContent = pr.name;
      el.append(dot, label);
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        cb.current.onSelect({ kind: 'region', id: pr.id });
      });
      markers.push(new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(pr.center).addTo(map));
      markerPos.current.set(el, pr.center);
      ipccEls.current.set(pr.id, el);
    });
    (map as unknown as { _updateMarkerVisibility?: () => void })._updateMarkerVisibility?.();
    return () => {
      markers.forEach((m) => {
        markerPos.current.delete(m.getElement());
        m.remove();
      });
      ipccEls.current.clear();
    };
  }, [ready, p.showIpcc, p.ipccGeo]);

  useEffect(() => {
    ipccEls.current.forEach((el, id) => {
      el.classList.remove('pin--up', 'pin--down', 'pin--none', 'pin--nodata', 'is-selected');
      el.classList.add(`pin--${p.ipccStates[id] ?? 'nodata'}`);
      if (p.target?.kind === 'region' && p.target.id === id) el.classList.add('is-selected');
    });
  }, [p.ipccStates, p.target, ready, p.showIpcc, p.ipccGeo]);

  // names of the IPCC regions appear on the globe once zoomed in; they always appear on hover or when selected
  useEffect(() => {
    const map = mapRef.current;
    const el = containerRef.current;
    if (!map || !ready || !el) return;
    const upd = () => el.classList.toggle('globe--zoomed', map.getZoom() >= 2.6);
    upd();
    map.on('zoom', upd);
    return () => {
      map.off('zoom', upd);
    };
  }, [ready]);

  // ---- IPCC region outlines ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('ipcc') as maplibregl.GeoJSONSource | undefined)?.setData(p.ipccGeo ?? EMPTY_FC);
  }, [p.ipccGeo, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    ['ipcc-fill', 'ipcc-line'].forEach((id) => map.setLayoutProperty(id, 'visibility', p.showIpcc ? 'visible' : 'none'));
  }, [p.showIpcc, ready]);

  // ---- trend map cells ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource('cells') as maplibregl.GeoJSONSource | undefined;
    src?.setData(p.mapData ? cellsGeoJSON(p.mapData, p.scheme, p.showNonSig) : EMPTY_FC);
  }, [p.mapData, p.scheme, p.showNonSig, ready]);

  // ---- hotspot markers ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    hotspotMarkers.current.forEach((m) => {
      markerPos.current.delete(m.getElement());
      m.remove();
    });
    hotspotMarkers.current = [];
    if (!p.showHotspots) return;
    p.hotspots.forEach((h) => {
      if (!h.centroid) return;
      const el = document.createElement('button');
      el.type = 'button';
      const sel = p.target?.kind === 'hotspot' && p.target.id === h.id;
      el.className = `hs hs--${h.direction === 'increasing' ? 'inc' : 'dec'}${sel ? ' is-selected' : ''}`;
      el.setAttribute('aria-label', `Hotspot: ${h.name}`);
      const g = document.createElement('span');
      g.className = 'hs__glyph';
      g.textContent = h.direction === 'increasing' ? '▲' : '▼';
      const label = document.createElement('span');
      label.className = 'hs__label';
      label.textContent = `${h.name} (${h.direction})`;
      el.append(g, label);
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        cb.current.onSelect({ kind: 'hotspot', id: h.id });
      });
      markerPos.current.set(el, [h.centroid[1], h.centroid[0]]);
      hotspotMarkers.current.push(
        new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([h.centroid[1], h.centroid[0]]).addTo(map),
      );
    });
    (map as unknown as { _updateMarkerVisibility?: () => void })._updateMarkerVisibility?.();
  }, [p.hotspots, p.showHotspots, p.target, ready]);

  // ---- colours for pins / hotspots follow the variable's colour scheme ----
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const c = endColors(p.scheme);
    el.style.setProperty('--c-pos', c.pos);
    el.style.setProperty('--c-neg', c.neg);
  }, [p.scheme]);

  // ---- imagery toggle + auto-rotate ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!map.getLayer(IMAGERY_LAYER)) return; // style not (re)loaded yet, e.g. right after a hot reload
    map.setLayoutProperty(IMAGERY_LAYER, 'visibility', p.showImagery ? 'visible' : 'none');
  }, [p.showImagery, ready]);

  useEffect(() => {
    const map = mapRef.current;
    spinRef.current = p.autoRotate;
    if (!map || !ready || !p.autoRotate) return;
    const c = map.getCenter();
    c.lng -= 3;
    map.easeTo({ center: c, duration: 1000, easing: (t) => t });
  }, [p.autoRotate, ready]);

  // ---- selection: outline, highlighted hotspot cells, camera ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const isIpcc = p.target?.kind === 'region' && p.target.id.startsWith('ar6:');
    const ipccFeat = isIpcc ? p.ipccGeo?.features.find((x) => (x.properties as { id: string }).id === p.target!.id) : undefined;
    const outline = map.getSource('region-outline') as maplibregl.GeoJSONSource | undefined;
    const mask = map.getSource('region-mask') as maplibregl.GeoJSONSource | undefined;
    let flyBox: [number, number, number, number] | null = null;
    if (p.target?.kind === 'custom') {
      const b = p.target.id.split(',').map(Number) as [number, number, number, number];
      outline?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [bboxPoly(b)] } });
      mask?.setData(EMPTY_FC);
    } else if (ipccFeat) {
      const polys: number[][][][] = ipccFeat.geometry.type === 'Polygon' ? [ipccFeat.geometry.coordinates] : (ipccFeat.geometry as GeoJSON.MultiPolygon).coordinates;
      const pts = polys.flatMap((pg) => pg[0]);
      flyBox = [Math.min(...pts.map((q) => q[0])), Math.min(...pts.map((q) => q[1])), Math.max(...pts.map((q) => q[0])), Math.max(...pts.map((q) => q[1]))];
      outline?.setData(ipccFeat as GeoJSON.Feature);
      const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
      mask?.setData({
        type: 'Feature', properties: {},
        geometry: { type: 'Polygon', coordinates: [world, ...polys.map((pg) => [...pg[0]].reverse())] },
      });
    } else {
      outline?.setData(EMPTY_FC);
      mask?.setData(EMPTY_FC);
    }
    const hl = map.getSource('hotspot-cells') as maplibregl.GeoJSONSource | undefined;
    hl?.setData(p.highlightCells ? cellsOutline(p.highlightCells) : EMPTY_FC);

    if (flyBox) {
      map.flyTo({
        center: [(flyBox[0] + flyBox[2]) / 2, (flyBox[1] + flyBox[3]) / 2],
        zoom: zoomFor(spanOf(flyBox)),
        speed: 0.9,
        offset: [-190, 0],
      });
    } else if (p.target?.kind === 'tile') {
      const [la, lo] = p.target.id.split(',').map(Number);
      map.easeTo({ center: [lo, la], zoom: Math.max(map.getZoom(), 2.6), duration: 800, offset: [-190, 0] });
    } else if (p.target?.kind === 'hotspot') {
      const h = p.hotspots.find((x) => x.id === p.target!.id);
      if (h?.centroid) {
        map.flyTo({ center: [h.centroid[1], h.centroid[0]], zoom: zoomFor(spanOf(h.bbox)), speed: 0.9, offset: [-190, 0] });
      }
    }
    if (!p.target && hadTarget.current) {
      // selection cleared: go back to the overview so the whole globe can be dragged again
      map.easeTo({ zoom: homeZoom.current, duration: 900, offset: [0, 0] });
    }
    hadTarget.current = !!p.target;
    // camera should move only when the selection changes, not when hotspots reload
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.target, p.highlightCells, ready, p.ipccGeo]);

  function resetView() {
    const map = mapRef.current;
    if (!map) return;
    cb.current.onSelect(null);
    map.easeTo({ center: [10, 25], zoom: homeZoom.current, pitch: 0, bearing: 0, duration: 900, offset: [0, 0] });
  }

  return (
    <>
      <div ref={containerRef} className="globe" />
      <button type="button" className="reset-btn" onClick={resetView} title="Zoom out to the whole globe">
        ⟲ Whole globe
      </button>
    </>
  );
}
