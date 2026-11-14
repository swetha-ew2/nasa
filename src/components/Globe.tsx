import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapFile, RegionInfo, Scheme, SeriesRecord, Target } from '../types';
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

export type PinState = 'up' | 'down' | 'none' | 'nodata';

interface Props {
  regions: RegionInfo[];
  pinStates: Record<string, PinState>;
  mapData: MapFile | null;
  scheme: Scheme;
  units: string;
  showNonSig: boolean;
  showHotspots: boolean;
  showPins: boolean;
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
  const pinEls = useRef<Map<string, HTMLElement>>(new Map());
  const hotspotMarkers = useRef<maplibregl.Marker[]>([]);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  /** DOM marker -> [lng, lat]; used to hide markers on the far side of the globe */
  const markerPos = useRef<Map<HTMLElement, [number, number]>>(new Map());
  const spinRef = useRef(false);
  const homeZoom = useRef(2);
  const hadTarget = useRef(false);
  const [ready, setReady] = useState(false);

  const cb = useRef({ onSelect: p.onSelect, onUserInteract: p.onUserInteract, units: p.units });
  cb.current = { onSelect: p.onSelect, onUserInteract: p.onUserInteract, units: p.units };

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

      // hover read-out for cells: what is changing here, and by how much
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'cell-popup', offset: 10 });
      popupRef.current = popup;
      map.on('mousemove', 'cells-fill', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const pr = f.properties as { v: number; sig: number; p: number | null };
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${pr.v > 0 ? '+' : ''}${fmt(Number(pr.v))}</strong> ${cb.current.units} per decade<br>` +
              (Number(pr.sig) === 1
                ? '<span class="pop-sig">significant trend</span>'
                : '<span class="pop-ns">not significant</span>') +
              (pr.p !== null && pr.p !== undefined ? ` · p = ${fmtP(Number(pr.p))}` : ''),
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

    map.on('click', () => cb.current.onSelect(null));
    const stopSpin = () => cb.current.onUserInteract();
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
      ro.disconnect();
      spinRef.current = false;
      pinEls.current.clear();
      hotspotMarkers.current = [];
      markerPos.current.clear();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- region pins (created once the regions are known) ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const markers: maplibregl.Marker[] = [];
    if (!p.showPins) return;
    p.regions
      .filter((r) => r.id !== 'global')
      .forEach((r) => {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'pin pin--nodata';
        el.setAttribute('aria-label', r.name);
        const dot = document.createElement('span');
        dot.className = 'pin__dot';
        const label = document.createElement('span');
        label.className = 'pin__label';
        label.textContent = r.name;
        el.append(dot, label);
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          cb.current.onSelect({ kind: 'region', id: r.id });
        });
        const [w, s, e2, n] = r.bbox;
        const pos: [number, number] = [(w + e2) / 2, (s + n) / 2];
        markers.push(new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat(pos).addTo(map));
        markerPos.current.set(el, pos);
        pinEls.current.set(r.id, el);
      });
    (map as unknown as { _updateMarkerVisibility?: () => void })._updateMarkerVisibility?.();
    return () => {
      markers.forEach((m) => {
        markerPos.current.delete(m.getElement());
        m.remove();
      });
      pinEls.current.clear();
    };
  }, [ready, p.regions, p.showPins]);

  // ---- pin state + selection (toggle only our own classes: MapLibre adds its own positioning classes) ----
  useEffect(() => {
    pinEls.current.forEach((el, id) => {
      el.classList.remove('pin--up', 'pin--down', 'pin--none', 'pin--nodata', 'is-selected');
      el.classList.add(`pin--${p.pinStates[id] ?? 'nodata'}`);
      if (p.target?.kind === 'region' && p.target.id === id) el.classList.add('is-selected');
    });
  }, [p.pinStates, p.target, ready, p.regions, p.showPins]);

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
    const region = p.target?.kind === 'region' ? p.regions.find((r) => r.id === p.target!.id) : undefined;
    const outline = map.getSource('region-outline') as maplibregl.GeoJSONSource | undefined;
    outline?.setData(
      region && region.id !== 'global'
        ? {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [[[region.bbox[0], region.bbox[1]], [region.bbox[2], region.bbox[1]], [region.bbox[2], region.bbox[3]], [region.bbox[0], region.bbox[3]], [region.bbox[0], region.bbox[1]]]],
            },
          }
        : EMPTY_FC,
    );
    const hl = map.getSource('hotspot-cells') as maplibregl.GeoJSONSource | undefined;
    hl?.setData(p.highlightCells ? cellsOutline(p.highlightCells) : EMPTY_FC);

    if (region && region.id !== 'global') {
      map.flyTo({
        center: [(region.bbox[0] + region.bbox[2]) / 2, (region.bbox[1] + region.bbox[3]) / 2],
        zoom: zoomFor(spanOf(region.bbox)),
        speed: 0.9,
        offset: [-190, 0],
      });
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
  }, [p.target, p.highlightCells, ready]);

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
