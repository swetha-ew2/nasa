export interface Example {
  question: string;
  about: string; // what the example looks at, in plain words
  variable: string;
  variableName: string;
  region: string | null;
  placeName: string;
}

export const EXAMPLES: Example[] = [
  {
    question: 'Is the planet warming?',
    about: 'The average temperature of the air near the ground, across the whole Earth, from 2005 to 2024.',
    variable: 't2m',
    variableName: 'Air temperature',
    region: 'global',
    placeName: 'Whole Earth',
  },
  {
    question: 'How fast is the sea rising?',
    about: 'Satellites measure the height of the ocean surface. See the global rise and where it is fastest.',
    variable: 'sea_level',
    variableName: 'Sea level',
    region: 'global',
    placeName: 'Whole Earth',
  },
  {
    question: 'Is the Mediterranean drying?',
    about: 'Soil moisture 10–40 cm down around the Mediterranean. It points downward but is not yet statistically significant, a good example of an early sign.',
    variable: 'soil_moist_10_40',
    variableName: 'Soil moisture',
    region: 'med',
    placeName: 'Mediterranean Basin',
  },
  {
    question: 'Is the Sahel greening?',
    about: 'How green the plant cover is, seen by satellite, in the dry belt south of the Sahara.',
    variable: 'ndvi',
    variableName: 'Vegetation greenness',
    region: 'sahel',
    placeName: 'Sahel',
  },
];
