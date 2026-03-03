/**
 * Historical route configuration
 * Defines trade routes and road networks for the Historical Routes panel
 */

export interface RouteConfig {
  id: string
  name: string
  group: string
  color: number
  type: 'land' | 'sea'
  era: string
}

export const ROUTE_GROUPS = [
  'Ancient Trade Routes',
  'Roman Roads (AWMC)'
] as const

export type RouteGroup = typeof ROUTE_GROUPS[number]

export const ROUTES: RouteConfig[] = [
  // Land routes
  { id: 'Silk Road (Northern Route)', name: 'Silk Road (Northern)', group: 'Ancient Trade Routes', color: 0xFFD700, type: 'land', era: '130 BC – 500 AD' },
  { id: 'Silk Road (Southern Route)', name: 'Silk Road (Southern)', group: 'Ancient Trade Routes', color: 0xFFC125, type: 'land', era: '130 BC – 500 AD' },
  { id: 'Amber Road', name: 'Amber Road', group: 'Ancient Trade Routes', color: 0xFFBF00, type: 'land', era: '1600 BC – 500 AD' },
  { id: 'Incense Route', name: 'Incense Route', group: 'Ancient Trade Routes', color: 0xE6BE8A, type: 'land', era: '7th c. BC – 2nd c. AD' },
  { id: 'Trans-Saharan Route (Western)', name: 'Trans-Saharan Route', group: 'Ancient Trade Routes', color: 0xC19A6B, type: 'land', era: '500 BC – 500 AD' },
  { id: 'Royal Road (Persian)', name: 'Royal Road (Persian)', group: 'Ancient Trade Routes', color: 0xB8860B, type: 'land', era: '500 BC – 330 BC' },
  { id: 'Via Maris', name: 'Via Maris', group: 'Ancient Trade Routes', color: 0xCD853F, type: 'land', era: 'Bronze Age – Roman' },
  { id: "King's Highway", name: "King's Highway", group: 'Ancient Trade Routes', color: 0xD2691E, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Inca Road (Qhapaq Ñan) - Main North-South', name: 'Inca Road (Qhapaq Ñan)', group: 'Ancient Trade Routes', color: 0x8B4513, type: 'land', era: '1400s AD' },
  { id: 'Maya Trade Route (Inland)', name: 'Maya Inland Route', group: 'Ancient Trade Routes', color: 0x228B22, type: 'land', era: '250 – 900 AD' },
  { id: 'Chaco Roads', name: 'Chaco Roads', group: 'Ancient Trade Routes', color: 0xA0522D, type: 'land', era: '850 – 1250 AD' },
  { id: 'Lapis Lazuli Route', name: 'Lapis Lazuli Route', group: 'Ancient Trade Routes', color: 0x26619C, type: 'land', era: '3000 BC – 500 BC' },
  { id: 'Via Regia', name: 'Via Regia', group: 'Ancient Trade Routes', color: 0x8B0000, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Salt Road (Trans-Saharan)', name: 'Salt Road', group: 'Ancient Trade Routes', color: 0xDEB887, type: 'land', era: 'Bronze Age – Roman' },
  { id: 'Grand Trunk Road', name: 'Grand Trunk Road', group: 'Ancient Trade Routes', color: 0x556B2F, type: 'land', era: '3rd c. BC – 500 AD' },
  // Sea routes
  { id: 'Spice Route (Maritime)', name: 'Spice Route (Maritime)', group: 'Ancient Trade Routes', color: 0xFF6347, type: 'sea', era: '3rd c. BC – 500 AD' },
  { id: 'Tin Route', name: 'Tin Route', group: 'Ancient Trade Routes', color: 0x708090, type: 'sea', era: '2000 BC – 500 BC' },
  { id: 'Maya Trade Route (Coastal)', name: 'Maya Coastal Route', group: 'Ancient Trade Routes', color: 0x2E8B57, type: 'sea', era: '250 – 900 AD' },
  { id: 'Maritime Silk Road', name: 'Maritime Silk Road', group: 'Ancient Trade Routes', color: 0x4169E1, type: 'sea', era: '2nd c. BC – 500 AD' },
  { id: 'Phoenician Sea Routes', name: 'Phoenician Sea Routes', group: 'Ancient Trade Routes', color: 0x800080, type: 'sea', era: '1500 BC – 300 BC' },
  { id: 'Egyptian Route to Punt', name: 'Egyptian Route to Punt', group: 'Ancient Trade Routes', color: 0xDAA520, type: 'sea', era: '2500 BC – 1100 BC' },
]

export const AWMC_ROADS_CONFIG = {
  id: 'awmc_roads',
  name: 'Roman Roads (AWMC)',
  group: 'Roman Roads (AWMC)' as RouteGroup,
  color: 0xDAA520,
  era: '300 BC – 400 AD',
  file: '/data/layers/awmc_roads.geojson',
  attribution: 'Data from Ancient World Mapping Center, UNC Chapel Hill (ODbL)'
}

export function getRouteById(id: string): RouteConfig | undefined {
  return ROUTES.find(r => r.id === id)
}
