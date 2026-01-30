// =============================================================================
// GLOBE SHADERS INDEX - Central export for all globe-related shader materials
// =============================================================================

// Dot materials - site markers with pop-in animation and sun lighting
export {
  createFrontDotMaterial,
  createDotShadowMaterial,
  createBackDotMaterial,
  updateDotMaterialUniforms,
  updateDotSize,
  updateDotSunDirection,
  updateDotSatelliteMode,
  updateDotsFadeProgress,
} from './dotMaterials'

// Line materials - vector layer lines (coastlines, borders, rivers, etc)
export {
  createFrontLineMaterial,
  createBackLineMaterial,
  updateLineMaterialUniforms,
  updateLineSunDirection,
  updateLineSatelliteMode,
  updateLineOpacity,
} from './lineMaterials'

// Empire materials - stencil-based polygon fills for historical territories
export {
  createStencilMaterial,
  createLandMaskStencilMaterial,
  createEmpireFillMaterial,
  updateEmpireMaterialUniforms,
  updateEmpireSunDirection,
  updateEmpireSatelliteMode,
  updateEmpireOpacity,
  // Empire hover effects
  EMPIRE_FILL_OPACITY,
  EMPIRE_BORDER_OPACITY,
  setEmpireHoverState,
  animateEmpireHover,
} from './empireMaterials'
