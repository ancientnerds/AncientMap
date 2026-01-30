// Barrel export for Globe rendering modules
export * from './empireRenderer'
// geoLabelSystem exports GeoLabel/GlobeLabel which conflict with vectorRenderer
// Export selectively to avoid conflicts
export {
  loadGeoLabels,
  handleLabelReload,
  updateGeoLabels,
  updateEmpireLabelsVisibility,
  type GeoLabelContext,
} from './geoLabelSystem'
// vectorRenderer also exports GeoLabel/GlobeLabel - use these as canonical
export * from './vectorRenderer'
export * from './mapboxEffects'
export * from './sceneInit'
export * from './animationLoop'
export * from './eventHandlers'
export * from './sitesRenderer'
export * from './paleoshorelineLoader'
export * from './measurementRenderer'
export * from './highlightedSitesRenderer'
// Site and empire hover utilities
export * from './siteProximityUtils'
export * from './empireHoverUtils'
