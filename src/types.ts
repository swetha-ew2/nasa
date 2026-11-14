export type Category = 'Atmosphere' | 'Land' | 'Water cycle' | 'Ocean' | 'Cryosphere';

/** How far the analysis pipeline supports this variable (placeholder values for now). */
export type AnalysisStatus = 'verified' | 'experimental' | 'catalog';

export interface Variable {
  id: string;
  name: string;
  category: Category;
  /** One-sentence plain-language definition for students / the public. */
  definition: string;
  units: string;
  source: string;
  record: string;
  status: AnalysisStatus;
}

/** Placeholder trend state used only to colour pins until real analysis exists. */
export type TrendStatus = 'increasing' | 'decreasing' | 'none' | 'pending';

export interface Region {
  id: string;
  name: string;
  lat: number;
  lon: number;
  /** [west, south, east, north] */
  bbox: [number, number, number, number];
  blurb: string;
  /** Variables suggested for this region (ids from variables.ts). */
  variableIds: string[];
  placeholderTrend: TrendStatus;
}
