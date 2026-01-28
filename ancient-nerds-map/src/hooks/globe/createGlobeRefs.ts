/**
 * createGlobeRefs - Factory to create the shared GlobeRefs container
 *
 * This factory creates all the refs that are shared across Globe hooks.
 * It mirrors the exact ref declarations from Globe.tsx to enable
 * incremental migration without breaking existing functionality.
 */

import { useRef } from 'react'
import * as THREE from 'three'
import type { GlobeRefs, SceneObjectRefs, GlobeLabel, MeasurementLabelData, MeasurementLineData, MeasurementMarkerData } from './types'
import type { SiteData } from '../../data/sites'
import type { VectorLayerKey } from '../../config/vectorLayers'
import type { GlobeLabelMesh } from '../../utils/LabelRenderer'
import { FadeManager } from '../../utils/FadeManager'
import type { MapboxGlobeService } from '../../services/MapboxGlobeService'
import type { DetailLevel } from '../../config/globeConstants'

/**
 * Hook to create and manage all Globe refs
 *
 * Usage:
 * ```typescript
 * const refs = useGlobeRefs()
 * // Pass refs to hooks: useGlobeScene(refs), useGlobeAnimation(refs), etc.
 * ```
 */
export function useGlobeRefs(): GlobeRefs {
  // ========== DOM Container Refs ==========
  const container = useRef<HTMLDivElement | null>(null)
  const mapboxContainer = useRef<HTMLDivElement | null>(null)
  const fps = useRef<HTMLDivElement | null>(null)

  // ========== Core Three.js Scene Refs ==========
  const scene = useRef<SceneObjectRefs | null>(null)

  // ========== Basemap Refs ==========
  const basemapMesh = useRef<THREE.Mesh | null>(null)
  const basemapBackMesh = useRef<THREE.Mesh | null>(null)
  const basemapTexture = useRef<THREE.Texture | null>(null)
  const currentBasemap = useRef<string>('')
  const basemapSectionMeshes = useRef<THREE.Mesh[]>([])
  const landMaskMesh = useRef<THREE.Mesh | null>(null)

  // ========== Stars and Visual Effects ==========
  const stars = useRef<THREE.Group | null>(null)
  const logoSprite = useRef<THREE.Sprite | null>(null)
  const logoMaterial = useRef<THREE.SpriteMaterial | null>(null)

  // ========== Shader Materials ==========
  const shaderMaterials = useRef<THREE.ShaderMaterial[]>([])
  const ledDotMaterial = useRef<THREE.ShaderMaterial | null>(null)

  // ========== Site/Dot Refs ==========
  const sites = useRef<SiteData[]>([])
  const selectedPoints = useRef<THREE.Points | null>(null)
  const selectedDotMaterial = useRef<THREE.ShaderMaterial | null>(null)
  const baseColors = useRef<Float32Array | null>(null)
  const sitePositions3D = useRef<Float32Array | null>(null)
  const validSites = useRef<SiteData[]>([])

  // ========== Label Refs ==========
  const labelGroup = useRef<THREE.Group | null>(null)
  const geoLabels = useRef<GlobeLabel[]>([])
  const allLabelMeshes = useRef<GlobeLabelMesh[]>([])
  const cuddleOffsets = useRef<Map<string, THREE.Vector3>>(new Map())
  const cuddleAnimations = useRef<Map<string, number>>(new Map())
  const layerLabels = useRef<Record<string, GlobeLabel[]>>({
    lakes: [],
    rivers: [],
    plateBoundaries: [],
    glaciers: [],
    coralReefs: [],
  })
  const visibleLabelNames = useRef<Set<string>>(new Set())
  const visibleAfterCollision = useRef<Set<string>>(new Set())
  const labelVisibilityState = useRef<Map<string, boolean>>(new Map())
  const lastCalculatedZoom = useRef<number>(-1)
  const labelUpdateThrottle = useRef<NodeJS.Timeout | null>(null)

  // ========== Vector Layer Refs ==========
  const frontLineLayers = useRef<Record<VectorLayerKey, THREE.Line[]>>({
    coastlines: [],
    countryBorders: [],
    rivers: [],
    lakes: [],
    glaciers: [],
    coralReefs: [],
    plateBoundaries: []
  })
  const backLineLayers = useRef<Record<VectorLayerKey, THREE.Line[]>>({
    coastlines: [],
    countryBorders: [],
    rivers: [],
    lakes: [],
    glaciers: [],
    coralReefs: [],
    plateBoundaries: []
  })
  const backLayersLoaded = useRef<Record<string, boolean>>({})
  const loading = useRef<Record<string, boolean>>({})

  // ========== Paleoshoreline Refs ==========
  const paleoshorelineLines = useRef<THREE.Line[]>([])
  const paleoshorelinePositionsCache = useRef<Map<string, Float32Array>>(new Map())
  const paleoshorelineLoadId = useRef<number>(0)
  const coastlinesWereActive = useRef<boolean>(true)

  // ========== Empire Border Refs ==========
  const empireBorderLines = useRef<Record<string, THREE.Line[]>>({})
  const empireLabels = useRef<Record<string, GlobeLabelMesh>>({})
  const regionLabels = useRef<Record<string, GlobeLabelMesh[]>>({})
  const regionData = useRef<Record<string, Array<{ name: string; lat: number; lng: number; years: number[] }>> | null>(null)
  const ancientCities = useRef<Record<string, GlobeLabelMesh[]>>({})
  const ancientCitiesData = useRef<Record<string, Array<{ name: string; lat: number; lng: number; years: number[]; type: string }>>>({})
  const empirePolygonFeatures = useRef<Record<string, Array<{ geometry: { type: string; coordinates: any } }>>>({})
  const empireLoadAbort = useRef<Record<string, AbortController>>({})
  const empireYearDebounce = useRef<Record<string, NodeJS.Timeout>>({})
  const globalTimelineThrottle = useRef<number>(0)
  const empireLabelPositionDebounce = useRef<Record<string, NodeJS.Timeout>>({})
  const empireYears = useRef<Record<string, number>>({})
  const showEmpireLabels = useRef<boolean>(true)
  const showAncientCities = useRef<boolean>(true)
  const visibleEmpires = useRef<Set<string>>(new Set())

  // ========== Measurement Tool Refs ==========
  const measurementObjects = useRef<THREE.Object3D[]>([])
  const measurementLabels = useRef<MeasurementLabelData[]>([])
  const measurementLines = useRef<MeasurementLineData[]>([])
  const measurementMarkers = useRef<MeasurementMarkerData[]>([])
  const measureMode = useRef<boolean | undefined>(undefined)
  const measureSnapEnabled = useRef<boolean | undefined>(undefined)
  const measurements = useRef<Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>>([])
  const currentMeasurePoints = useRef<Array<{ coords: [number, number]; snapped: boolean }>>([])

  // ========== Proximity Filter Refs ==========
  const proximityCircle = useRef<THREE.Group | null>(null)
  const proximityCenter = useRef<THREE.Sprite | null>(null)
  const proximityPreview = useRef<THREE.Group | null>(null)
  const proximityPreviewCenter = useRef<THREE.Sprite | null>(null)
  const proximityCircleCenterPos = useRef<THREE.Vector3 | null>(null)
  const proximityRaycaster = useRef<THREE.Raycaster | null>(null)
  const hoverCenter = useRef<[number, number] | null>(null)
  const lastHoverCallbackTime = useRef<number>(0)
  const lastHoverCoords = useRef<[number, number] | null>(null)

  // ========== Tooltip/Hover State Refs ==========
  const frozenSite = useRef<SiteData | null>(null)
  const hoveredSite = useRef<SiteData | null>(null)
  const currentHoveredSite = useRef<SiteData | null>(null)
  const lastSeenSite = useRef<SiteData | null>(null)
  const showTooltips = useRef<boolean>(true)
  const isFrozen = useRef<boolean>(false)
  const frozenAt = useRef<number>(0)
  const sitesPassedDuringFreeze = useRef<number>(0)
  const lastSiteId = useRef<string | null>(null)
  const firstFreezeComplete = useRef<boolean>(false)
  const frozenTooltipPos = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const highlightFrozen = useRef<boolean>(false)
  const isHoveringTooltip = useRef<boolean>(false)
  const isHoveringList = useRef<boolean>(false)

  // ========== List Highlight Refs ==========
  const highlightGlows = useRef<THREE.Sprite[]>([])
  const listHighlightedSites = useRef<SiteData[]>([])
  const listHighlightedPositions = useRef<Map<string, { x: number; y: number }>>(new Map())

  // ========== Mouse/Input Refs ==========
  const lastMousePos = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const lastMoveTime = useRef<number>(Date.now())
  const lastCoordsUpdate = useRef<number>(0)
  const lastScaleUpdate = useRef<number>(0)
  const lastHoverCheck = useRef<number>(0)

  // ========== Animation/Warp Refs ==========
  const warpStartTime = useRef<number | null>(null)
  const warpProgress = useRef<number>(0)
  const warpLinearProgress = useRef<number>(0)
  const warpInitialCameraPos = useRef<THREE.Vector3 | null>(null)
  const warpTargetCameraPos = useRef<THREE.Vector3 | null>(null)
  const warpCompleteForLabels = useRef<boolean>(false)
  const dotsAnimationComplete = useRef<boolean>(false)
  const logoAnimationStarted = useRef<boolean>(false)

  // ========== Camera/View Refs ==========
  const isAutoRotating = useRef<boolean>(true)
  const manualRotation = useRef<boolean>(false)
  const cameraAnimation = useRef<number | null>(null)
  const kmPerPixel = useRef<number>(1)

  // ========== Zoom Control Refs ==========
  const isManualZoom = useRef<boolean>(false)
  const isMapboxZoom = useRef<boolean>(false)
  const isSliderZoom = useRef<boolean>(false)
  const isWheelZoom = useRef<boolean>(false)
  const wheelCursorLatLng = useRef<{ lat: number; lng: number } | null>(null)
  const justEnteredMapbox = useRef<boolean>(false)
  const mapboxBaseZoom = useRef<number>(50)

  // ========== Mapbox Refs ==========
  const mapboxService = useRef<MapboxGlobeService | null>(null)
  const showMapbox = useRef<boolean>(false)
  const prevShowMapbox = useRef<boolean>(false)
  const mapboxTransitioning = useRef<boolean>(false)

  // ========== Satellite Mode Refs ==========
  const satelliteMode = useRef<boolean>(false)
  const highResGrayLoaded = useRef<boolean>(false)
  const highResSatelliteLoaded = useRef<boolean>(false)

  // ========== Loading State Refs ==========
  const texturesReady = useRef<boolean>(false)
  const backgroundLoadingComplete = useRef<boolean>(false)
  const layersReadyCalled = useRef<boolean>(false)

  // ========== Page/Context State Refs ==========
  const isPageVisible = useRef<boolean>(true)
  const webglContextLost = useRef<boolean>(false)
  const needsLabelReload = useRef<boolean>(false)
  const splashDone = useRef<boolean | undefined>(undefined)
  const siteClickJustHappened = useRef<boolean>(false)

  // ========== Visibility Refs ==========
  const geoLabelsVisible = useRef<boolean>(false)
  const labelTypesVisible = useRef<Record<string, boolean>>({})
  const vectorLayers = useRef<Record<VectorLayerKey, boolean>>({
    coastlines: true,
    countryBorders: true,
    rivers: false,
    lakes: false,
    glaciers: false,
    coralReefs: false,
    plateBoundaries: false
  })
  const detailLevel = useRef<DetailLevel>('medium')
  const dotSize = useRef<number>(6)
  const showCoordsBeforeContribute = useRef<boolean>(true)

  // ========== Contribute Picker Refs ==========
  const isContributePickerActive = useRef<boolean>(false)

  // ========== Low FPS Tracking ==========
  const lowFpsStartTime = useRef<number | null>(null)

  // ========== Callback Refs ==========
  const onSiteClick = useRef<((site: SiteData | null) => void) | undefined>(undefined)
  const onSiteSelect = useRef<((siteId: string | null, ctrlKey: boolean) => void) | undefined>(undefined)
  const onMeasurePointAdd = useRef<((coords: [number, number], snapped: boolean) => void) | undefined>(undefined)
  const onMeasurementComplete = useRef<((start: [number, number], end: [number, number]) => void) | undefined>(undefined)
  const onContributeMapConfirm = useRef<(() => void) | undefined>(undefined)

  // ========== Update Function Refs ==========
  const updateGeoLabels = useRef<(() => void) | null>(null)
  const updateEmpireLabelsVisibility = useRef<((cameraDir: THREE.Vector3) => void) | null>(null)
  const updateMeasurementLabelsVisibility = useRef<((cameraDir: THREE.Vector3, hideBackside?: number) => void) | null>(null)

  // ========== Fade Manager ==========
  const fadeManager = useRef<FadeManager>(new FadeManager())

  // ========== Animation Frame Refs ==========
  const animationId = useRef<{ value: number }>({ value: 0 })
  const zoom = useRef<number>(0)

  // ========== Label Loading State Refs ==========
  const labelsLoaded = useRef<boolean>(false)
  const labelsLoading = useRef<boolean>(false)
  const totalLabelsCount = useRef<number>(0)

  // ========== Previous State Tracking Refs ==========
  const prevDetailLevel = useRef<DetailLevel | null>(null)
  const prevBackDetailLevel = useRef<DetailLevel | null>(null)
  const prevSeaLevel = useRef<number>(-120)
  const prevReplaceCoastlines = useRef<boolean>(false)
  const prevPaleoshorelineVisible = useRef<boolean>(false)

  // ========== Texture Cache Refs ==========
  const textureCache = useRef<{
    grayBasemap: THREE.Texture | null
    satellite: THREE.Texture | null
  }>({
    grayBasemap: null,
    satellite: null
  })

  // ========== Preloading Refs ==========
  const vectorPreloaded = useRef<boolean>(false)

  // ========== Additional Callback Refs ==========
  const onEmpireYearsChange = useRef<((years: Record<string, number>) => void) | undefined>(undefined)

  // ========== Contribute Picker Refs ==========
  const contributeLastHoverTime = useRef<number>(0)
  const wasContributePickerActive = useRef<boolean>(false)

  return {
    // DOM Container Refs
    container,
    mapboxContainer,
    fps,

    // Core Three.js Scene Refs
    scene,

    // Basemap Refs
    basemapMesh,
    basemapBackMesh,
    basemapTexture,
    currentBasemap,
    basemapSectionMeshes,
    landMaskMesh,

    // Stars and Visual Effects
    stars,
    logoSprite,
    logoMaterial,

    // Shader Materials
    shaderMaterials,
    ledDotMaterial,

    // Site/Dot Refs
    sites,
    selectedPoints,
    selectedDotMaterial,
    baseColors,
    sitePositions3D,
    validSites,

    // Label Refs
    labelGroup,
    geoLabels,
    allLabelMeshes,
    cuddleOffsets,
    cuddleAnimations,
    layerLabels,
    visibleLabelNames,
    visibleAfterCollision,
    labelVisibilityState,
    lastCalculatedZoom,
    labelUpdateThrottle,

    // Vector Layer Refs
    frontLineLayers,
    backLineLayers,
    backLayersLoaded,
    loading,

    // Paleoshoreline Refs
    paleoshorelineLines,
    paleoshorelinePositionsCache,
    paleoshorelineLoadId,
    coastlinesWereActive,

    // Empire Border Refs
    empireBorderLines,
    empireLabels,
    regionLabels,
    regionData,
    ancientCities,
    ancientCitiesData,
    empirePolygonFeatures,
    empireLoadAbort,
    empireYearDebounce,
    globalTimelineThrottle,
    empireLabelPositionDebounce,
    empireYears,
    showEmpireLabels,
    showAncientCities,
    visibleEmpires,

    // Measurement Tool Refs
    measurementObjects,
    measurementLabels,
    measurementLines,
    measurementMarkers,
    measureMode,
    measureSnapEnabled,
    measurements,
    currentMeasurePoints,

    // Proximity Filter Refs
    proximityCircle,
    proximityCenter,
    proximityPreview,
    proximityPreviewCenter,
    proximityCircleCenterPos,
    proximityRaycaster,
    hoverCenter,
    lastHoverCallbackTime,
    lastHoverCoords,

    // Tooltip/Hover State Refs
    frozenSite,
    hoveredSite,
    currentHoveredSite,
    lastSeenSite,
    showTooltips,
    isFrozen,
    frozenAt,
    sitesPassedDuringFreeze,
    lastSiteId,
    firstFreezeComplete,
    frozenTooltipPos,
    highlightFrozen,
    isHoveringTooltip,
    isHoveringList,

    // List Highlight Refs
    highlightGlows,
    listHighlightedSites,
    listHighlightedPositions,

    // Mouse/Input Refs
    lastMousePos,
    lastMoveTime,
    lastCoordsUpdate,
    lastScaleUpdate,
    lastHoverCheck,

    // Animation/Warp Refs
    warpStartTime,
    warpProgress,
    warpLinearProgress,
    warpInitialCameraPos,
    warpTargetCameraPos,
    warpCompleteForLabels,
    dotsAnimationComplete,
    logoAnimationStarted,

    // Camera/View Refs
    isAutoRotating,
    manualRotation,
    cameraAnimation,
    kmPerPixel,

    // Zoom Control Refs
    isManualZoom,
    isMapboxZoom,
    isSliderZoom,
    isWheelZoom,
    wheelCursorLatLng,
    justEnteredMapbox,
    mapboxBaseZoom,

    // Mapbox Refs
    mapboxService,
    showMapbox,
    prevShowMapbox,
    mapboxTransitioning,

    // Satellite Mode Refs
    satelliteMode,
    highResGrayLoaded,
    highResSatelliteLoaded,

    // Loading State Refs
    texturesReady,
    backgroundLoadingComplete,
    layersReadyCalled,

    // Page/Context State Refs
    isPageVisible,
    webglContextLost,
    needsLabelReload,
    splashDone,
    siteClickJustHappened,

    // Visibility Refs
    geoLabelsVisible,
    labelTypesVisible,
    vectorLayers,
    detailLevel,
    dotSize,
    showCoordsBeforeContribute,

    // Contribute Picker Refs
    isContributePickerActive,

    // Low FPS Tracking
    lowFpsStartTime,

    // Callback Refs
    onSiteClick,
    onSiteSelect,
    onMeasurePointAdd,
    onMeasurementComplete,
    onContributeMapConfirm,

    // Update Function Refs
    updateGeoLabels,
    updateEmpireLabelsVisibility,
    updateMeasurementLabelsVisibility,

    // Fade Manager
    fadeManager,

    // Animation Frame Refs
    animationId,
    zoom,

    // Label Loading State Refs
    labelsLoaded,
    labelsLoading,
    totalLabelsCount,

    // Previous State Tracking Refs
    prevDetailLevel,
    prevBackDetailLevel,
    prevSeaLevel,
    prevReplaceCoastlines,
    prevPaleoshorelineVisible,

    // Texture Cache Refs
    textureCache,

    // Preloading Refs
    vectorPreloaded,

    // Additional Callback Refs
    onEmpireYearsChange,

    // Contribute Picker Refs
    contributeLastHoverTime,
    wasContributePickerActive,
  }
}
