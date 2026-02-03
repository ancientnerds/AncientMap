/**
 * Globe Types - Shared types and interfaces for Globe hooks
 *
 * This file defines the central ref container (GlobeRefs) that is shared
 * across all Globe hooks, enabling coordination and communication.
 */

import type * as THREE from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { SiteData } from '../../data/sites'
import type { VectorLayerKey } from '../../config/vectorLayers'
import type { GlobeLabelMesh } from '../../utils/LabelRenderer'
import type { FadeManager } from '../../utils/FadeManager'
import type { MapboxGlobeService } from '../../services/MapboxGlobeService'
import type { DetailLevel } from '../../config/globeConstants'

/**
 * Core Three.js refs - the essential scene objects
 */
export interface SceneCoreRefs {
  renderer: React.MutableRefObject<THREE.WebGLRenderer | null>
  scene: React.MutableRefObject<THREE.Scene | null>
  camera: React.MutableRefObject<THREE.PerspectiveCamera | null>
  controls: React.MutableRefObject<OrbitControls | null>
  globe: React.MutableRefObject<THREE.Mesh | null>
}

/**
 * Scene object refs for composite scene object
 * This matches the sceneRef structure in Globe.tsx
 */
export interface SceneObjectRefs {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  points: THREE.Points | null
  backPoints: THREE.Points | null
  shadowPoints: THREE.Points | null
  globe: THREE.Mesh
}

/**
 * Geographic label structure
 */
export interface GeoLabel {
  name: string
  lat: number
  lng: number
  type: 'continent' | 'country' | 'capital' | 'ocean' | 'sea' | 'region' | 'mountain' | 'desert' | 'lake' | 'river' | 'metropol' | 'city' | 'plate' | 'glacier' | 'coralReef'
  rank: number
  hidden?: boolean
  layerBased?: boolean
  country?: string
  national?: boolean
  detailLevel?: number
}

/**
 * Globe-pinned label with 3D position
 */
export interface GlobeLabel {
  label: GeoLabel
  mesh: GlobeLabelMesh
  position: THREE.Vector3
}

/**
 * Measurement label with positioning data
 */
export interface MeasurementLabelData {
  label: THREE.Sprite
  midpoint: THREE.Vector3
  targetWidth: number
  targetHeight: number
}

/**
 * Measurement line with path data
 */
export interface MeasurementLineData {
  line: THREE.Line
  points: THREE.Vector3[]
}

/**
 * Measurement marker with position
 */
export interface MeasurementMarkerData {
  marker: THREE.Object3D
  position: THREE.Vector3
}

/**
 * GlobeRefs - Central ref container shared across all Globe hooks
 *
 * This interface mirrors ALL refs from Globe.tsx to enable hooks to
 * access and modify the same underlying data structures.
 */
export interface GlobeRefs {
  // ========== DOM Container Refs ==========
  container: React.MutableRefObject<HTMLDivElement | null>
  mapboxContainer: React.MutableRefObject<HTMLDivElement | null>
  fps: React.MutableRefObject<HTMLDivElement | null>

  // ========== Core Three.js Scene Refs ==========
  scene: React.MutableRefObject<SceneObjectRefs | null>

  // ========== Basemap Refs ==========
  basemapMesh: React.MutableRefObject<THREE.Mesh | null>
  basemapBackMesh: React.MutableRefObject<THREE.Mesh | null>
  basemapTexture: React.MutableRefObject<THREE.Texture | null>
  currentBasemap: React.MutableRefObject<string>
  basemapSectionMeshes: React.MutableRefObject<THREE.Mesh[]>
  landMaskMesh: React.MutableRefObject<THREE.Mesh | null>

  // ========== Stars and Visual Effects ==========
  stars: React.MutableRefObject<THREE.Group | null>
  logoSprite: React.MutableRefObject<THREE.Sprite | null>
  logoMaterial: React.MutableRefObject<THREE.SpriteMaterial | null>

  // ========== Shader Materials ==========
  shaderMaterials: React.MutableRefObject<THREE.ShaderMaterial[]>
  ledDotMaterial: React.MutableRefObject<THREE.ShaderMaterial | null>

  // ========== Site/Dot Refs ==========
  sites: React.MutableRefObject<SiteData[]>
  selectedPoints: React.MutableRefObject<THREE.Points | null>
  selectedDotMaterial: React.MutableRefObject<THREE.ShaderMaterial | null>
  baseColors: React.MutableRefObject<Float32Array | null>
  sitePositions3D: React.MutableRefObject<Float32Array | null>
  validSites: React.MutableRefObject<SiteData[]>

  // ========== Label Refs ==========
  labelGroup: React.MutableRefObject<THREE.Group | null>
  geoLabels: React.MutableRefObject<GlobeLabel[]>
  allLabelMeshes: React.MutableRefObject<GlobeLabelMesh[]>
  cuddleOffsets: React.MutableRefObject<Map<string, THREE.Vector3>>
  cuddleAnimations: React.MutableRefObject<Map<string, number>>
  layerLabels: React.MutableRefObject<Record<string, GlobeLabel[]>>
  visibleLabelNames: React.MutableRefObject<Set<string>>
  visibleAfterCollision: React.MutableRefObject<Set<string>>
  labelVisibilityState: React.MutableRefObject<Map<string, boolean>>
  lastCalculatedZoom: React.MutableRefObject<number>
  labelUpdateThrottle: React.MutableRefObject<NodeJS.Timeout | null>

  // ========== Vector Layer Refs ==========
  frontLineLayers: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  backLineLayers: React.MutableRefObject<Record<VectorLayerKey, THREE.Line[]>>
  backLayersLoaded: React.MutableRefObject<Record<string, boolean>>
  loading: React.MutableRefObject<Record<string, boolean>>

  // ========== Paleoshoreline Refs ==========
  paleoshorelineLines: React.MutableRefObject<THREE.Line[]>
  paleoshorelinePositionsCache: React.MutableRefObject<Map<string, Float32Array>>
  paleoshorelineLoadId: React.MutableRefObject<number>
  coastlinesWereActive: React.MutableRefObject<boolean>

  // ========== Empire Border Refs ==========
  empireBorderLines: React.MutableRefObject<Record<string, THREE.Line[]>>
  empireLabels: React.MutableRefObject<Record<string, GlobeLabelMesh>>
  regionLabels: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  regionData: React.MutableRefObject<Record<string, Array<{ name: string; lat: number; lng: number; years: number[] }>> | null>
  ancientCities: React.MutableRefObject<Record<string, GlobeLabelMesh[]>>
  ancientCitiesData: React.MutableRefObject<Record<string, Array<{ name: string; lat: number; lng: number; years: number[]; type: string }>>>
  empirePolygonFeatures: React.MutableRefObject<Record<string, Array<{ geometry: { type: string; coordinates: any } }>>>
  empireLoadAbort: React.MutableRefObject<Record<string, AbortController>>
  empireYearDebounce: React.MutableRefObject<Record<string, NodeJS.Timeout>>
  globalTimelineThrottle: React.MutableRefObject<number>
  empireLabelPositionDebounce: React.MutableRefObject<Record<string, NodeJS.Timeout>>
  empireYears: React.MutableRefObject<Record<string, number>>
  showEmpireLabels: React.MutableRefObject<boolean>
  showAncientCities: React.MutableRefObject<boolean>
  visibleEmpires: React.MutableRefObject<Set<string>>
  hoveredEmpire: React.MutableRefObject<string | null>
  empireFillMeshes: React.MutableRefObject<Record<string, THREE.Mesh[]>>

  // ========== Measurement Tool Refs ==========
  measurementObjects: React.MutableRefObject<THREE.Object3D[]>
  measurementLabels: React.MutableRefObject<MeasurementLabelData[]>
  measurementLines: React.MutableRefObject<MeasurementLineData[]>
  measurementMarkers: React.MutableRefObject<MeasurementMarkerData[]>
  measureMode: React.MutableRefObject<boolean | undefined>
  measureSnapEnabled: React.MutableRefObject<boolean | undefined>
  measurements: React.MutableRefObject<Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>>
  currentMeasurePoints: React.MutableRefObject<Array<{ coords: [number, number]; snapped: boolean }>>

  // ========== Proximity Filter Refs ==========
  proximityCircle: React.MutableRefObject<THREE.Group | null>
  proximityCenter: React.MutableRefObject<THREE.Sprite | null>
  proximityPreview: React.MutableRefObject<THREE.Group | null>
  proximityPreviewCenter: React.MutableRefObject<THREE.Sprite | null>
  proximityCircleCenterPos: React.MutableRefObject<THREE.Vector3 | null>
  proximityRaycaster: React.MutableRefObject<THREE.Raycaster | null>
  hoverCenter: React.MutableRefObject<[number, number] | null>
  lastHoverCallbackTime: React.MutableRefObject<number>
  lastHoverCoords: React.MutableRefObject<[number, number] | null>

  // ========== Tooltip/Hover State Refs ==========
  frozenSite: React.MutableRefObject<SiteData | null>
  hoveredSite: React.MutableRefObject<SiteData | null>
  currentHoveredSite: React.MutableRefObject<SiteData | null>
  lastSeenSite: React.MutableRefObject<SiteData | null>
  showTooltips: React.MutableRefObject<boolean>
  isFrozen: React.MutableRefObject<boolean>
  frozenAt: React.MutableRefObject<number>
  sitesPassedDuringFreeze: React.MutableRefObject<number>
  lastSiteId: React.MutableRefObject<string | null>
  firstFreezeComplete: React.MutableRefObject<boolean>
  frozenTooltipPos: React.MutableRefObject<{ x: number; y: number }>
  highlightFrozen: React.MutableRefObject<boolean>
  isHoveringTooltip: React.MutableRefObject<boolean>
  isHoveringList: React.MutableRefObject<boolean>

  // ========== List Highlight Refs ==========
  highlightGlows: React.MutableRefObject<THREE.Sprite[]>
  listHighlightedSites: React.MutableRefObject<SiteData[]>
  listHighlightedPositions: React.MutableRefObject<Map<string, { x: number; y: number }>>

  // ========== Mouse/Input Refs ==========
  lastMousePos: React.MutableRefObject<{ x: number; y: number }>
  lastMoveTime: React.MutableRefObject<number>
  lastCoordsUpdate: React.MutableRefObject<number>
  lastScaleUpdate: React.MutableRefObject<number>
  lastHoverCheck: React.MutableRefObject<number>

  // ========== Animation/Warp Refs ==========
  warpStartTime: React.MutableRefObject<number | null>
  warpProgress: React.MutableRefObject<number>
  warpLinearProgress: React.MutableRefObject<number>
  warpInitialCameraPos: React.MutableRefObject<THREE.Vector3 | null>
  warpTargetCameraPos: React.MutableRefObject<THREE.Vector3 | null>
  warpCompleteForLabels: React.MutableRefObject<boolean>
  dotsAnimationComplete: React.MutableRefObject<boolean>
  logoAnimationStarted: React.MutableRefObject<boolean>

  // ========== Camera/View Refs ==========
  isAutoRotating: React.MutableRefObject<boolean>
  manualRotation: React.MutableRefObject<boolean>
  cameraAnimation: React.MutableRefObject<number | null>
  kmPerPixel: React.MutableRefObject<number>

  // ========== Zoom Control Refs ==========
  isManualZoom: React.MutableRefObject<boolean>
  isMapboxZoom: React.MutableRefObject<boolean>
  isSliderZoom: React.MutableRefObject<boolean>
  isWheelZoom: React.MutableRefObject<boolean>
  wheelCursorLatLng: React.MutableRefObject<{ lat: number; lng: number } | null>
  justEnteredMapbox: React.MutableRefObject<boolean>
  mapboxBaseZoom: React.MutableRefObject<number>

  // ========== Mapbox Refs ==========
  mapboxService: React.MutableRefObject<MapboxGlobeService | null>
  showMapbox: React.MutableRefObject<boolean>
  prevShowMapbox: React.MutableRefObject<boolean>
  mapboxTransitioning: React.MutableRefObject<boolean>

  // ========== Satellite Mode Refs ==========
  satelliteMode: React.MutableRefObject<boolean>
  highResGrayLoaded: React.MutableRefObject<boolean>
  highResSatelliteLoaded: React.MutableRefObject<boolean>

  // ========== Loading State Refs ==========
  texturesReady: React.MutableRefObject<boolean>
  backgroundLoadingComplete: React.MutableRefObject<boolean>
  layersReadyCalled: React.MutableRefObject<boolean>

  // ========== Page/Context State Refs ==========
  isPageVisible: React.MutableRefObject<boolean>
  webglContextLost: React.MutableRefObject<boolean>
  needsLabelReload: React.MutableRefObject<boolean>
  splashDone: React.MutableRefObject<boolean | undefined>
  siteClickJustHappened: React.MutableRefObject<boolean>

  // ========== Visibility Refs ==========
  geoLabelsVisible: React.MutableRefObject<boolean>
  labelTypesVisible: React.MutableRefObject<Record<string, boolean>>
  vectorLayers: React.MutableRefObject<Record<VectorLayerKey, boolean>>
  detailLevel: React.MutableRefObject<DetailLevel>
  dotSize: React.MutableRefObject<number>
  showCoordsBeforeContribute: React.MutableRefObject<boolean>

  // ========== Contribute Picker Refs ==========
  isContributePickerActive: React.MutableRefObject<boolean>

  // ========== Low FPS Tracking ==========
  lowFpsStartTime: React.MutableRefObject<number | null>

  // ========== Callback Refs ==========
  onSiteClick: React.MutableRefObject<((site: SiteData | null) => void) | undefined>
  onSiteSelect: React.MutableRefObject<((siteId: string | null, ctrlKey: boolean) => void) | undefined>
  onEmpireClick: React.MutableRefObject<((empireId: string, defaultYear?: number, yearOptions?: number[]) => void) | undefined>
  onMeasurePointAdd: React.MutableRefObject<((coords: [number, number], snapped: boolean) => void) | undefined>
  onMeasurementComplete: React.MutableRefObject<((start: [number, number], end: [number, number]) => void) | undefined>
  onContributeMapConfirm: React.MutableRefObject<(() => void) | undefined>

  // ========== Update Function Refs ==========
  updateGeoLabels: React.MutableRefObject<(() => void) | null>
  updateEmpireLabelsVisibility: React.MutableRefObject<((cameraDir: THREE.Vector3) => void) | null>
  updateMeasurementLabelsVisibility: React.MutableRefObject<((cameraDir: THREE.Vector3, hideBackside?: number) => void) | null>

  // ========== Fade Manager ==========
  fadeManager: React.MutableRefObject<FadeManager>

  // ========== Animation Frame Refs ==========
  animationId: React.MutableRefObject<{ value: number }>
  zoom: React.MutableRefObject<number>

  // ========== Label Loading State Refs ==========
  labelsLoaded: React.MutableRefObject<boolean>
  labelsLoading: React.MutableRefObject<boolean>
  totalLabelsCount: React.MutableRefObject<number>

  // ========== Previous State Tracking Refs ==========
  prevDetailLevel: React.MutableRefObject<DetailLevel | null>
  prevBackDetailLevel: React.MutableRefObject<DetailLevel | null>
  prevSeaLevel: React.MutableRefObject<number>
  prevReplaceCoastlines: React.MutableRefObject<boolean>
  prevPaleoshorelineVisible: React.MutableRefObject<boolean>

  // ========== Texture Cache Refs ==========
  textureCache: React.MutableRefObject<{
    grayBasemap: THREE.Texture | null
    satellite: THREE.Texture | null
  }>

  // ========== Preloading Refs ==========
  vectorPreloaded: React.MutableRefObject<boolean>

  // ========== Additional Callback Refs ==========
  onEmpireYearsChange: React.MutableRefObject<((years: Record<string, number>) => void) | undefined>

  // ========== Contribute Picker Refs ==========
  contributeLastHoverTime: React.MutableRefObject<number>
  wasContributePickerActive: React.MutableRefObject<boolean>
}

/**
 * Animation callback registration for the RAF loop
 */
export interface AnimationCallback {
  id: string
  priority: number  // Lower numbers run first
  callback: (delta: number, elapsed: number) => void
}

/**
 * Layer loading state
 */
export interface LayerLoadingState {
  isLoading: boolean
  progress?: number
  error?: Error | null
}
