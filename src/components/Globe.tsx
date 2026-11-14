import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Region } from '../types';

// NASA GIBS "Blue Marble" static imagery (no date needed, no login needed).
// GIBS serves WMTS tiles as {z}/{row}/{col}, which equals MapLibre's {z}/{y}/{x}.
const GIBS_BLUE_MARBLE =
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg';

const OUTLINE_SOURCE = 'region-outline';
const IMAGERY_LAYER = 'gibs-blue-marble';

// Inline style: no third-party style file to depend on. If the imagery tiles
// cannot load (offline, blocked), you still get a plain dark-blue globe with pins.
const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  projection: { type: 'globe' },
  sources: {
    [IMAGERY_LAYER]: {
      type: 'raster',
      tiles: [GIBS_BLUE_MARBLE],
      tileSize: 256,
      maxzoom: 8,
      attribution: 'NASA GIBS',
    },
  },
  layers: [
    { id: 'ocean', type: 'background', paint: { 'background-color': '#0b2a4a' } },
    { id: IMAGERY_LAYER, type: 'raster', source: IMAGERY_LAYER },
  ],
};

interface Props {
  regions: Region[];
  selectedRegionId: string | null;
  /** Region ids to emphasise (e.g. regions where the chosen variable applies). null = no filter. */
  highlightRegionIds: Set<string> | null;
  showImagery: boolean;
  autoRotate: boolean;
  onSelectRegion: (id: string | null) => void;
  onUserInteract: () => void;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

function bboxToFeature(b: [number, number, number, number]): GeoJSON.Feature {
  const [w, s, e, n] = b;
  return {
    type: 'Feature',
    properties: {},
    geometry: {
      type: 'Polygon',
      coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    },
  };
}

export default function Globe({
  regions,
  selectedRegionId,
  highlightRegionIds,
  showImagery,
  autoRotate,
  onSelectRegion,
  onUserInteract,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pinEls = useRef<Map<string, HTMLElement>>(new Map());
  const spinRef = useRef(false);
  const [ready, setReady] = useState(false);

  // Keep latest callbacks in refs so map listeners never go stale.
  const cb = useRef({ onSelectRegion, onUserInteract });
  cb.current = { onSelectRegion, onUserInteract };

  // ---- create the map once ----
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: [10, 25],
      zoom: 1.6,
      minZoom: 1,
      maxZoom: 8,
      attributionControl: false,
    });
    mapRef.current = map;

    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: 'Imagery: NASA GIBS / ESDIS',
      }),
      'bottom-right',
    );
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');

    map.on('style.load', () => {
      map.setProjection({ type: 'globe' });

      // Atmosphere glow. Wrapped so a version difference can never break the app.
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

      map.addSource(OUTLINE_SOURCE, { type: 'geojson', data: EMPTY_FC });
      map.addLayer({
        id: 'region-outline-fill',
        type: 'fill',
        source: OUTLINE_SOURCE,
        paint: { 'fill-color': '#5ad1ff', 'fill-opacity': 0.14 },
      });
      map.addLayer({
        id: 'region-outline-line',
        type: 'line',
        source: OUTLINE_SOURCE,
        paint: { 'line-color': '#7fe0ff', 'line-width': 2, 'line-dasharray': [2, 1] },
      });

      setReady(true);
    });

    // Click on empty globe = deselect.
    map.on('click', () => cb.current.onSelectRegion(null));

    // Any manual interaction stops the auto-rotation.
    const stopSpin = () => cb.current.onUserInteract();
    map.on('mousedown', stopSpin);
    map.on('touchstart', stopSpin);
    map.on('wheel', stopSpin);

    // Auto-rotate loop: each easeTo ends with moveend, which starts the next step.
    map.on('moveend', () => {
      if (!spinRef.current) return;
      const c = map.getCenter();
      c.lng -= 3;
      map.easeTo({ center: c, duration: 1000, easing: (t) => t });
    });

    // Pins (DOM markers). Style the children, never the root: MapLibre positions
    // the root element with its own transform.
    regions.forEach((r) => {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `pin pin--${r.placeholderTrend}`;
      el.setAttribute('aria-label', r.name);

      const dot = document.createElement('span');
      dot.className = 'pin__dot';
      const label = document.createElement('span');
      label.className = 'pin__label';
      label.textContent = r.name;
      el.append(dot, label);

      el.addEventListener('click', (e) => {
        e.stopPropagation();
        cb.current.onSelectRegion(r.id);
      });

      new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([r.lon, r.lat])
        .addTo(map);
      pinEls.current.set(r.id, el);
    });

    // Keep the canvas sized correctly when the layout changes.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      spinRef.current = false;
      pinEls.current.clear();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
    // Regions are static for now; create the map once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- imagery toggle ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setLayoutProperty(IMAGERY_LAYER, 'visibility', showImagery ? 'visible' : 'none');
  }, [showImagery, ready]);

  // ---- auto-rotate ----
  useEffect(() => {
    const map = mapRef.current;
    spinRef.current = autoRotate;
    if (!map || !ready || !autoRotate) return;
    const c = map.getCenter();
    c.lng -= 3;
    map.easeTo({ center: c, duration: 1000, easing: (t) => t });
  }, [autoRotate, ready]);

  // ---- pin styling: selected / highlighted / dimmed ----
  useEffect(() => {
    pinEls.current.forEach((el, id) => {
      el.classList.toggle('is-selected', id === selectedRegionId);
      el.classList.toggle('is-match', !!highlightRegionIds && highlightRegionIds.has(id));
      el.classList.toggle('is-dim', !!highlightRegionIds && !highlightRegionIds.has(id));
    });
  }, [selectedRegionId, highlightRegionIds]);

  // ---- region outline + camera move on selection ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const region = regions.find((r) => r.id === selectedRegionId) ?? null;

    const src = map.getSource(OUTLINE_SOURCE) as maplibregl.GeoJSONSource | undefined;
    src?.setData(region ? bboxToFeature(region.bbox) : EMPTY_FC);

    if (region) {
      map.flyTo({
        center: [region.lon, region.lat],
        zoom: 3.4,
        speed: 0.9,
        // shift the target left so it isn't hidden behind the side panel
        offset: [-190, 0],
      });
    }
  }, [selectedRegionId, ready, regions]);

  return <div ref={containerRef} className="globe" />;
}
