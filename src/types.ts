// Shapes of the files in public/data (written by export_frontend.py).

export type Scheme = 'heat' | 'water' | 'green' | 'neutral';

export interface VariableInfo {
  id: string; // short slug, e.g. "t2m"
  var_id: string; // pipeline id
  name: string;
  definition: string;
  units: string;
  category: string;
  family: string;
  role: 'headline' | 'data-driven';
  scheme: Scheme;
  source: string;
  record: string;
  grid: string;
  test_used: string;
  map_color_limit: number;
  global_slope_per_decade: number | null;
  global_ci95: [number, number] | null;
  global_p: number | null;
  sig_area_fraction: number;
  sig_positive_area: number;
  sig_negative_area: number;
  divergence: number;
  finding: string;
  stability: number | null;
}

export interface RegionInfo {
  id: string;
  name: string;
  bbox: [number, number, number, number]; // west, south, east, north
  blurb: string;
  suggested_variables: string[];
  analysed_variables: string[];
}

export interface Manifest {
  title: string;
  window: string;
  grid: string;
  methods: Record<string, string>;
  caveats: string[];
  not_available: string;
  variables: VariableInfo[];
  regions: RegionInfo[];
}

export interface MapFile {
  var: string;
  lat: number[];
  lon: number[];
  units_per_decade: string;
  color_limit: number;
  slope: (number | null)[];
  significant: number[];
  p: (number | null)[];
  effect_size: (number | null)[];
}

/** One region (box or global) or one hotspot, with its series and statistics. */
export interface SeriesRecord {
  id: string;
  name: string;
  bbox: [number, number, number, number];
  cover: number | null;
  status: 'ok' | 'no_data' | 'insufficient_coverage';
  months?: number[];
  raw?: (number | null)[];
  anomaly?: (number | null)[];
  slope_per_decade?: number;
  ci95?: [number, number];
  p?: number;
  p_mk?: number;
  p_ols?: number;
  test_used?: 'ols' | 'mk';
  residuals_clean?: boolean;
  snr?: number;
  n_months?: number;
  sen_intercept?: number;
  ci_excludes_zero?: boolean;
  significant_fdr?: boolean;
  direction?: string;
  // hotspots only
  variable?: string;
  centroid?: [number, number];
  n_cells?: number;
  cells?: [number, number][];
  exploratory?: boolean;
  note?: string;
  consistent_in_both_halves?: boolean;
  halves_slope_per_decade?: [number, number];
}

export interface SeriesFile {
  var: string;
  units: string;
  regions: SeriesRecord[];
  hotspots: SeriesRecord[];
}

export interface InterestingItem {
  var: string;
  var_name: string;
  units: string;
  region: string;
  region_name: string;
  slope_per_decade: number;
  ci95: [number, number];
  p: number;
  snr: number;
  ci_excludes_zero: boolean;
  text: string;
}

export interface Story {
  region: string;
  region_name: string;
  n_variables: number;
  variables: string[];
  text: string;
}

export interface Interesting {
  criteria: string;
  items: InterestingItem[];
  stories: Story[];
}

export type Target = { kind: 'region' | 'hotspot'; id: string };

/** Legacy shape used by src/data/regions.ts, which the analysis pipeline still reads for the region boxes. */
export interface Region {
  id: string;
  name: string;
  lat: number;
  lon: number;
  bbox: [number, number, number, number];
  blurb: string;
  variableIds: string[];
  placeholderTrend: 'increasing' | 'decreasing' | 'none' | 'pending';
}
