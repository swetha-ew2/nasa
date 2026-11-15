// The question flow: theme -> question -> place. Each question points at exactly one variable (by its short id).
export interface JourneyQuestion {
  q: string;
  about: string;
  variable: string;
}
export interface JourneyTheme {
  id: string;
  label: string;
  blurb: string;
  questions: JourneyQuestion[];
}

export const THEMES: JourneyTheme[] = [
  {
    id: 'heat',
    label: 'Heat and warming',
    blurb: 'Is it getting warmer, and where?',
    questions: [
      { q: 'Is the planet warming?', about: 'The temperature of the air near the ground and the sea surface.', variable: 't2m' },
      { q: 'Is the sea surface warming?', about: 'The temperature of the top layer of the ocean.', variable: 'sst' },
      { q: 'Is the ground itself warming?', about: 'The temperature of the top 10 cm of the soil.', variable: 'soil_temp' },
      { q: 'Is the lower atmosphere warming?', about: 'The height of the 500 hPa pressure level, which rises as the air below it warms.', variable: 'h500' },
    ],
  },
  {
    id: 'water',
    label: 'Rain and drought',
    blurb: 'Is it getting wetter or drier?',
    questions: [
      { q: 'Is it raining more or less?', about: 'How much rain and snow falls per day.', variable: 'precip' },
      { q: 'Is the surface soil drying out?', about: 'How full of water the top layer of soil is.', variable: 'soil_wetness_top' },
      { q: 'Is the deeper soil drying out?', about: 'Water held in the soil 10 to 40 cm down.', variable: 'soil_moist_10_40' },
      { q: 'Do two land models agree on soil moisture?', about: 'Soil water in a second land model, a useful cross-check.', variable: 'soil_moist_vic2' },
      { q: 'Is the water stored on land changing?', about: 'All the water held on land: soil, groundwater, snow and surface water.', variable: 'tws' },
      { q: 'Is storm runoff changing?', about: 'Rain water that runs over the ground instead of soaking in.', variable: 'runoff' },
    ],
  },
  {
    id: 'ocean',
    label: 'Oceans',
    blurb: 'How is the sea changing?',
    questions: [
      { q: 'How fast is the sea rising?', about: 'Satellites measure the height of the ocean surface.', variable: 'sea_level' },
      { q: 'Is the sea surface warming?', about: 'The temperature of the top layer of the ocean.', variable: 'sst' },
    ],
  },
  {
    id: 'ice',
    label: 'Ice and snow',
    blurb: 'Is the frozen world shrinking?',
    questions: [
      { q: 'Is snow cover changing?', about: 'The share of the land covered by snow each month.', variable: 'snow' },
      { q: 'Is the sea rising as ice melts?', about: 'Sea level is one of the clearest signs of melting ice and warming oceans.', variable: 'sea_level' },
    ],
  },
  {
    id: 'plants',
    label: 'Plants and land',
    blurb: 'Is the land greener or drier?',
    questions: [
      { q: 'Is the land getting greener?', about: 'How green and dense the plant cover is, seen by satellite.', variable: 'ndvi' },
      { q: 'Is more water evaporating from land?', about: 'Water returned to the air from soil and plants.', variable: 'evap_land' },
      { q: 'Is the land using more energy to evaporate water?', about: 'Heat carried away from the surface by evaporation.', variable: 'latent_heat' },
    ],
  },
  {
    id: 'air',
    label: 'Air and sunlight',
    blurb: 'Is the sky changing?',
    questions: [
      { q: 'Is the air getting hazier?', about: 'How much sunlight is blocked by dust, smoke and other airborne particles.', variable: 'aod' },
      { q: 'Is more sunlight reaching the surface?', about: 'Incoming solar energy at the ground or sea.', variable: 'sw_down' },
      { q: 'Is the land absorbing more sunlight?', about: 'Sunlight absorbed by the land: incoming minus reflected.', variable: 'sw_net' },
      { q: 'Are cloud tops getting warmer or colder?', about: 'Colder tops mean taller clouds.', variable: 'cloud_top_temp' },
      { q: 'Is more water evaporating into the air?', about: 'Evaporation from the surface, over land and sea.', variable: 'evap_surface' },
    ],
  },
];
