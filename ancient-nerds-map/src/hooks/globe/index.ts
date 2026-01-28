/**
 * Globe hooks - Custom React hooks for Globe component state and logic
 *
 * These hooks extract state management and side effects from Globe.tsx
 * to create a clean orchestrator pattern.
 */

// Core types and factory
export * from './types'
export { useGlobeRefs } from './createGlobeRefs'

// Simple state hooks (Group 2)
export { useUIState } from './useUIState'
export { useLabelVisibility } from './useLabelVisibility'
export type { LabelTypesVisible } from './useLabelVisibility'
export { usePaleoshoreline } from './usePaleoshoreline'
export { useProximityFilter } from './useProximityFilter'
export { useMeasurementTool } from './useMeasurementTool'
export type { MeasurePoint, Measurement, MeasureUnit } from './useMeasurementTool'

// Medium complexity hooks (Group 3)
export { useMapboxSync } from './useMapboxSync'
export { useGlobeEvents } from './useGlobeEvents'
export { useVectorLayers } from './useVectorLayers'
export { useGlobeZoom } from './useGlobeZoom'
export { useSiteTooltips } from './useSiteTooltips'
export { useHighlightedSites } from './useHighlightedSites'
export { useFlyToAnimation } from './useFlyToAnimation'
export { useSatelliteMode } from './useSatelliteMode'
export { useContributePicker } from './useContributePicker'
export { useScreenshot } from './useScreenshot'
export { useRotationControl } from './useRotationControl'
export { useFullscreen } from './useFullscreen'
export { useCursorMode } from './useCursorMode'
export { useStarsVisibility } from './useStarsVisibility'
export { useTextureLoading } from './useTextureLoading'
export { useLayersReady } from './useLayersReady'
export { useTooltipHandlers } from './useTooltipHandlers'

// Complex hooks (Group 4)
export { useGlobeScene } from './useGlobeScene'
export type { SceneRefs } from './useGlobeScene'
export { useEmpireBorders } from './useEmpireBorders'
export { useGlobeAnimation } from './useGlobeAnimation'
export { useGeoLabels } from './useGeoLabels'
export type { GeoLabel, GlobeLabel, VectorLayerVisibility } from './useGeoLabels'
