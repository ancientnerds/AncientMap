// =============================================================================
// SHADERS INDEX - Central export for all shader materials
// =============================================================================

// Re-export all globe shaders from the new location
export * from './globe'

// Legacy exports for backward compatibility
// These are now deprecated - prefer importing from './globe' directly
export {
  createFrontLineMaterial as createFrontMaterial,
  createBackLineMaterial as createBackMaterial,
  updateLineMaterialUniforms,
} from './globe/lineMaterials'

export {
  createFrontDotMaterial,
  createBackDotMaterial,
  updateDotMaterialUniforms,
  updateDotSize,
} from './globe/dotMaterials'

export {
  createStencilMaterial,
  createLandMaskStencilMaterial,
  createEmpireFillMaterial,
  updateEmpireMaterialUniforms as updatePolygonMaterialUniforms,
} from './globe/empireMaterials'
