/** what the question flow hands to the app once the user has chosen a question and a place */
export interface Example {
  question: string;
  about: string; // what it looks at, in plain words
  variable: string;
  variableName: string;
  region: string | null; // a region id, or null
  hotspot?: string | null; // a hotspot id (used for "where is it changing most?")
  placeName: string;
}
