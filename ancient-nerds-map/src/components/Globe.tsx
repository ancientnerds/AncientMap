import { useEffect, useState, useCallback, useMemo } from 'react'
import * as THREE from 'three'
import { SiteData, getDataSource } from '../data/sites'
import { FilterMode } from '../App'
import { offlineFetch, OfflineFetch } from '../services/OfflineFetch'
import { useOffline } from '../contexts/OfflineContext'
import { EMPIRES } from '../config/empireData'
import { LAYER_CONFIG, getLayerUrl, type VectorLayerKey, type VectorLayerVisibility } from '../config/vectorLayers'
import { fadeLabelIn, fadeLabelOut } from '../utils/LabelRenderer'
import { createProximityCircle, createCenterMarker, disposeGroup, disposeSprite } from '../utils/proximityHelpers'
import { CoordinateDisplay, ScaleBar, ContributePickerHint, HardwareWarning, TooltipOverlay, MapboxOfflineWarning } from './Globe/overlays'
import { ZoomControls, SocialLinks, OptionsPanel, MapLayersPanel, HistoricalLayersSection, EmpireBordersPanel } from './Globe/panels'
import { ScreenshotControls } from './Globe/controls'
import { useUIState, useLabelVisibility, usePaleoshoreline, useEmpireBorders, useMapboxSync, useGlobeRefs, useGlobeZoom, useSiteTooltips, useHighlightedSites, useFlyToAnimation, useSatelliteMode, useContributePicker, useScreenshot, useRotationControl, useFullscreen, useCursorMode, useStarsVisibility, useTextureLoading, useLayersReady, useTooltipHandlers } from '../hooks/globe'
import {
  loadEmpireBorders as loadEmpireBordersImpl,
  removeEmpireFromGlobe as removeEmpireFromGlobeImpl,
  loadEmpireBordersForYear as loadEmpireBordersForYearImpl,
  updateEmpireLabelText as updateEmpireLabelTextImpl,
  animateEmpireLabelPosition as animateEmpireLabelPositionImpl,
  loadRegionLabels as loadRegionLabelsImpl,
  removeRegionLabels as removeRegionLabelsImpl,
  loadAncientCities as loadAncientCitiesImpl,
  removeAncientCities as removeAncientCitiesImpl,
  type GlobeRenderContext,
} from './Globe/rendering/empireRenderer'
import {
  createMapboxInitEffect,
  createAutoSwitchEffect,
  createModeSwitchEffect,
  createSitesSyncEffect,
  createMeasurementsSyncEffect,
  createProximityCircleSyncEffect,
  createSelectedSitesSyncEffect,
  type MapboxInitEffectDeps,
  type AutoSwitchEffectDeps,
  type ModeSwitchEffectDeps,
  type SitesSyncEffectDeps,
  type MeasurementsSyncEffectDeps,
  type ProximityCircleSyncEffectDeps,
  type SelectedSitesSyncEffectDeps,
} from './Globe/rendering/mapboxEffects'
import {
  loadGeoLabels as loadGeoLabelsImpl,
  handleLabelReload as handleLabelReloadImpl,
  updateGeoLabels as updateGeoLabelsImpl,
  updateEmpireLabelsVisibility as updateEmpireLabelsVisibilityImpl,
  type GeoLabelContext,
} from './Globe/rendering/geoLabelSystem'
import {
  loadFrontLayer as loadFrontLayerImpl,
  loadBackLayer as loadBackLayerImpl,
  type VectorRendererContext,
} from './Globe/rendering/vectorRenderer'
import { initializeScene, type SceneInitOptions } from './Globe/rendering/sceneInit'
import { runAnimationLoop, type AnimationLoopContext } from './Globe/rendering/animationLoop'
import {
  setupEventHandlers,
  type EventHandlerRefs,
  type EventHandlerSetters,
  type EventHandlerCallbacks,
  type EventHandlerSceneObjects,
} from './Globe/rendering/eventHandlers'
import {
  loadPaleoshoreline as loadPaleoshorelineImpl,
  disposePaleoshoreline,
  type PaleoshorelineContext,
} from './Globe/rendering/paleoshorelineLoader'
import {
  renderMeasurements,
  type MeasurementRendererContext,
} from './Globe/rendering/measurementRenderer'
import {
  createSitePoints,
  cleanupPoints,
  type SitesRendererOptions,
} from './Globe/rendering/sitesRenderer'

interface ProximityState {
  center: [number, number] | null
  radius: number
  isSettingOnGlobe: boolean
}

interface GlobeProps {
  sites: (SiteData & { isInsideProximity?: boolean })[]
  filterMode: FilterMode
  sourceColors?: Record<string, string>
  countryColors?: Record<string, string>
  highlightedSiteId?: string | null  // Site ID hovered in search/proximity results list
  isHoveringList?: boolean  // True when hovering over search/proximity results list
  listFrozenSiteIds?: string[]  // Site IDs frozen from click in list (supports multi-select with Ctrl)
  openPopupIds?: string[]  // Site IDs with open popups (tooltips hidden for these)
  onSiteClick?: (site: SiteData | null) => void  // Opens popup
  onTooltipClick?: (site: SiteData) => void  // Opens popup or restores minimized popup
  onSiteSelect?: (siteId: string | null, ctrlKey: boolean) => void  // Selects site (shows ring + tooltip), null = deselect all
  flyTo?: [number, number] | null  // [lng, lat] coordinates to fly to
  isLoading?: boolean  // Show loading state (disables clicks)
  splashDone?: boolean  // True when splash screen has closed (triggers warp animation)
  proximity?: ProximityState  // Proximity filter state
  onProximitySet?: (coords: [number, number]) => void  // Callback when position is set on globe
  onProximityHover?: (coords: [number, number] | null) => void  // Callback when hovering in proximity mode
  initialPosition?: [number, number] | null  // [lng, lat] initial camera position (user location)
  onLayersReady?: () => void  // Callback when essential layers (coastlines, borders) are loaded
  // Contribute feature
  onContributeClick?: () => void  // Callback when contribute button is clicked
  // AI Agent feature
  onAIAgentClick?: () => void  // Callback when AI agent button is clicked
  onDisclaimerClick?: () => void  // Callback when disclaimer link is clicked
  isContributeMapPickerActive?: boolean  // True when map picker mode is active
  onContributeMapHover?: (coords: [number, number] | null) => void  // Callback on hover (like proximity)
  onContributeMapConfirm?: () => void  // Callback when user clicks to confirm coordinates
  onContributeMapCancel?: () => void  // Callback when user cancels coordinate selection
  // Selection undo/redo
  canUndoSelection?: boolean
  onUndoSelection?: () => void
  canRedoSelection?: boolean
  onRedoSelection?: () => void
  // Measurement tool
  measureMode?: boolean
  measurements?: Array<{ id: string; points: [[number, number], [number, number]]; snapped: [boolean, boolean]; color: string }>  // Completed measurements
  currentMeasurePoints?: Array<{ coords: [number, number]; snapped: boolean }>  // Points being drawn for current measurement
  selectedMeasurementId?: string | null
  measureSnapEnabled?: boolean
  measureUnit?: 'km' | 'miles'
  currentMeasurementColor?: string // Color for the measurement currently being drawn
  onMeasurePointAdd?: (coords: [number, number], snapped: boolean) => void
  onMeasurementComplete?: (start: [number, number], end: [number, number]) => void
  onMeasurementSelect?: (id: string | null) => void
  onMeasurementDelete?: (id: string) => void
  // Random mode - hide all dots except selected
  randomModeActive?: boolean
  // Proximity filter - hide dots outside proximity ring
  searchWithinProximity?: boolean
  // Historical borders age sync
  onAgeRangeSync?: (range: [number, number]) => void  // Callback to sync age slider with empire periods
  // Empire filter callbacks (for "Within empires" feature)
  onVisibleEmpiresChange?: (empireIds: Set<string>) => void
  onEmpireYearsChange?: (years: Record<string, number>) => void
  onEmpirePolygonsLoaded?: (empireId: string, year: number, features: any[]) => void
  // Offline mode
  onOfflineClick?: () => void  // Callback when offline button is clicked
  isOffline?: boolean  // Whether currently offline (no network)
}

export default function Globe({ sites, filterMode, sourceColors, countryColors, highlightedSiteId, isHoveringList, listFrozenSiteIds = [], openPopupIds: _openPopupIds = [], onSiteClick, onTooltipClick, onSiteSelect, flyTo, isLoading, splashDone, proximity, onProximitySet, onProximityHover, initialPosition, onLayersReady, onContributeClick, onAIAgentClick, onDisclaimerClick, isContributeMapPickerActive, onContributeMapHover, onContributeMapConfirm, onContributeMapCancel, canUndoSelection, onUndoSelection, canRedoSelection, onRedoSelection, measureMode, measurements = [], currentMeasurePoints = [], selectedMeasurementId, measureSnapEnabled, measureUnit = 'km', currentMeasurementColor = '#FFCC00', onMeasurePointAdd, onMeasurementComplete, onMeasurementSelect: _onMeasurementSelect, onMeasurementDelete: _onMeasurementDelete, randomModeActive, searchWithinProximity, onAgeRangeSync, onVisibleEmpiresChange, onEmpireYearsChange, onEmpirePolygonsLoaded, onOfflineClick, isOffline }: GlobeProps) {
  const refs = useGlobeRefs()

  // Batch destructure refs
  const {
    container: containerRef, mapboxContainer: mapboxContainerRef, mapboxService: mapboxServiceRef,
    fps: fpsRef, logoSprite: logoSpriteRef, logoMaterial: logoMaterialRef,
    onSiteClick: onSiteClickRef, splashDone: splashDoneRef, siteClickJustHappened: siteClickJustHappenedRef,
    measureMode: measureModeRef, onMeasurePointAdd: onMeasurePointAddRef, onMeasurementComplete: onMeasurementCompleteRef,
    measureSnapEnabled: measureSnapEnabledRef, measurements: measurementsRef, currentMeasurePoints: currentMeasurePointsRef,
    scene: sceneRef, selectedPoints: selectedPointsRef, selectedDotMaterial: selectedDotMaterialRef,
    measurementObjects: measurementObjectsRef, measurementLabels: measurementLabelsRef,
    measurementLines: measurementLinesRef, measurementMarkers: measurementMarkersRef,
    labelGroup: labelGroupRef, sites: sitesRef,
  } = refs

  // Sync callback refs with current values
  onSiteClickRef.current = onSiteClick
  splashDoneRef.current = splashDone
  measureModeRef.current = measureMode
  onMeasurePointAddRef.current = onMeasurePointAdd
  onMeasurementCompleteRef.current = onMeasurementComplete
  measureSnapEnabledRef.current = measureSnapEnabled
  measurementsRef.current = measurements
  currentMeasurePointsRef.current = currentMeasurePoints
  const [sceneReady, setSceneReady] = useState(false)
  const [softwareRendering, setSoftwareRendering] = useState(false)
  const [warningDismissed, setWarningDismissed] = useState(false)
  const [gpuName, setGpuName] = useState<string | null>(null)
  const {
    backgroundLoadingComplete: backgroundLoadingCompleteRef, warpStartTime: warpStartTimeRef,
    warpProgress: warpProgressRef, dotsAnimationComplete: dotsAnimationCompleteRef,
    warpInitialCameraPos: warpInitialCameraPosRef, warpTargetCameraPos: warpTargetCameraPosRef,
    warpLinearProgress: warpLinearProgressRef, warpCompleteForLabels: warpCompleteForLabelsRef,
    logoAnimationStarted: logoAnimationStartedRef,
  } = refs

  // Custom Hooks
  const ui = useUIState({ initialShowCoordinates: true })
  const { showTooltips, showCoordinates, showScale, hudScale, hudScalePreview, hudVisible, dotSize } = ui

  const labels = useLabelVisibility({ initialGeoLabelsVisible: false })
  const { starsVisible, geoLabelsVisible, labelTypesExpanded, labelTypesVisible } = labels

  const paleo = usePaleoshoreline()
  const { seaLevel, sliderSeaLevel, paleoshorelineVisible, replaceCoastlines, isLoadingPaleoshoreline } = paleo

  const empires = useEmpireBorders({ onAgeRangeSync, onVisibleEmpiresChange, onEmpireYearsChange, onEmpirePolygonsLoaded })
  const {
    visibleEmpires, setVisibleEmpires, visibleEmpiresRef,
    empiresWithAgeSync, setEmpiresWithAgeSync,
    loadingEmpires, setLoadingEmpires, loadedEmpires, setLoadedEmpires,
    expandedRegions, setExpandedRegions,
    empireYears, setEmpireYears, empireYearsRef, empireYearOptions, setEmpireYearOptions,
    empireDefaultYears, setEmpireDefaultYears, empireCentroids, setEmpireCentroids,
    globalTimelineEnabled, setGlobalTimelineEnabled, globalTimelineYear, setGlobalTimelineYear,
    showEmpireLabels, setShowEmpireLabels, showEmpireLabelsRef,
    showAncientCities, setShowAncientCities, showAncientCitiesRef,
    empireBordersWindowOpen, setEmpireBordersWindowOpen, empireBordersHeight, setEmpireBordersHeight,
    empireBorderLinesRef, empireLabelsRef, regionLabelsRef, ancientCitiesRef,
    regionDataRef, ancientCitiesDataRef, empirePolygonFeaturesRef,
    empireLoadAbortRef, empireYearDebounceRef, globalTimelineThrottleRef
  } = empires

  const [vectorLayers, setVectorLayers] = useState<VectorLayerVisibility>({
    coastlines: true,
    countryBorders: true,
    rivers: false,
    lakes: false,
    coralReefs: false,
    glaciers: false,
    plateBoundaries: false
  })
  const [tileLayers, setTileLayers] = useState<{ satellite: boolean; streets: boolean }>({
    satellite: false,
    streets: false
  })
  const [mapLayersMinimized, setMapLayersMinimized] = useState(false)
  const coastlinesWereActive = refs.coastlinesWereActive
  const empireLabelPositionDebounceRef = refs.empireLabelPositionDebounce

  // Offline context - needed for layer availability and Mapbox warning
  const { isOffline: contextIsOffline, cachedSourceIds, cachedLayerIds, hasMapboxTilesCached } = useOffline()

  const mapboxSync = useMapboxSync({
    mapboxServiceRef,
    camera: sceneRef.current?.camera,
    isOffline: contextIsOffline,
    hasMapboxTilesCached
  })
  // Destructure for convenient access (avoiding conflicts with local declarations)
  const {
    showMapbox, setShowMapbox, showMapboxRef,
    mapboxTransitioningRef, prevShowMapboxRef,
    satelliteModeRef,
    showMapboxOfflineWarning, setShowMapboxOfflineWarning
  } = mapboxSync

  const globeZoom = useGlobeZoom({ refs, showMapbox })
  const { zoom, setZoom, detailLevel, isZoomedIn } = globeZoom

  const siteTooltips = useSiteTooltips({
    refs,
    highlightedSiteId,
    listFrozenSiteIds,
    sites,
  })
  const {
    hoveredSite, setHoveredSite,
    frozenSite, setFrozenSite,
    tooltipPos, setTooltipPos,
    isFrozen, setIsFrozen,
    tooltipSiteOnFront, setTooltipSiteOnFront,
  } = siteTooltips

  // Tooltip mouse handlers
  const { handleTooltipMouseEnter, handleTooltipMouseLeave } = useTooltipHandlers({
    refs,
    setIsFrozen,
    setFrozenSite,
  })

  // Highlighted Sites: list highlighted sites state and rendering
  const highlightedSitesHook = useHighlightedSites({
    refs,
    highlightedSiteId,
    listFrozenSiteIds,
    showMapbox,
    sites,
  })
  const {
    listHighlightedSites, setListHighlightedSites,
    listHighlightedPositions, setListHighlightedPositions,
  } = highlightedSitesHook

  // Fly-to animation: camera movement to coordinates from search results
  useFlyToAnimation({ refs, flyTo })

  // Satellite mode: toggle between gray basemap and satellite imagery
  useSatelliteMode({ refs, satellite: tileLayers.satellite, vectorLayers, showMapbox, mapboxServiceRef })

  // Contribute picker: map picker mode for adding new sites
  useContributePicker({
    refs,
    isActive: isContributeMapPickerActive,
    showCoordinates,
    setShowCoordinates: ui.setShowCoordinates,
    onHover: onContributeMapHover,
    onCancel: onContributeMapCancel,
  })

  // Screenshot: capture globe viewport
  const { handleScreenshot } = useScreenshot()

  const { isPlaying, toggle } = useRotationControl({ refs, isZoomedIn, isHoveringList: isHoveringList ?? false })

  // Fullscreen: toggle and sync fullscreen state
  const { isFullscreen, toggleFullscreen } = useFullscreen()

  // Cursor mode: crosshair cursor for globe, proximity/measure mode handling
  useCursorMode({
    refs,
    proximityIsSettingOnGlobe: proximity?.isSettingOnGlobe,
    measureMode: measureMode ?? false,
  })

  // Stars visibility with fade animation
  useStarsVisibility({
    refs,
    starsVisible,
  })

  // Texture loading and application
  const { texturesReady, backgroundLoadingComplete, lowFpsReady } = useTextureLoading({
    refs,
    sceneReady,
  })

  // Layers ready coordination hook called below (after labelsLoaded and layersLoaded are declared)

  const [cursorCoords, setCursorCoords] = useState<{ lat: number, lon: number } | null>(null)
  const [scaleBar, setScaleBar] = useState<{ km: number, pixels: number } | null>(null)
  const [lowFps, setLowFps] = useState(false)
  const {
    kmPerPixel: kmPerPixelRef, lowFpsStartTime: lowFpsStartTimeRef, dotSize: dotSizeRef,
    detailLevel: detailLevelRef, showTooltips: showTooltipsRef, isFrozen: isFrozenRef,
    frozenSite: frozenSiteRef, hoveredSite: hoveredSiteRef, lastMousePos: lastMousePosRef,
    isHoveringTooltip: isHoveringTooltipRef, currentHoveredSite: currentHoveredSiteRef,
    frozenAt: frozenAtRef, lastMoveTime: lastMoveTimeRef, sitesPassedDuringFreeze: sitesPassedDuringFreezeRef,
    lastSiteId: lastSiteIdRef, lastSeenSite: lastSeenSiteRef, firstFreezeComplete: firstFreezeCompleteRef,
    frozenTooltipPos: frozenTooltipPosRef, highlightFrozen: highlightFrozenRef,
    lastCoordsUpdate: lastCoordsUpdateRef, lastScaleUpdate: lastScaleUpdateRef, lastHoverCheck: lastHoverCheckRef,
  } = refs
  const [dataSourceIndicator, setDataSourceIndicator] = useState<'postgres' | 'json' | 'offline' | 'error' | ''>('')

  // Update data source indicator when sites load
  useEffect(() => {
    const source = getDataSource()
    if (source) {
      setDataSourceIndicator(source)
    }
  }, [sites])

  // Calculate dynamic range for global timeline from enabled empires
  const globalTimelineRange = useMemo(() => {
    const enabledEmpires = EMPIRES.filter(e => visibleEmpires.has(e.id))
    if (enabledEmpires.length === 0) return { min: -3000, max: 1900 }
    return {
      min: Math.min(...enabledEmpires.map(e => e.startYear)),
      max: Math.max(...enabledEmpires.map(e => e.endYear))
    }
  }, [visibleEmpires])

  // Clamp globalTimelineYear to valid range when range changes
  useEffect(() => {
    if (globalTimelineEnabled) {
      const clamped = Math.max(globalTimelineRange.min, Math.min(globalTimelineRange.max, globalTimelineYear))
      if (clamped !== globalTimelineYear) {
        setGlobalTimelineYear(clamped)
      }
    }
  }, [globalTimelineRange, globalTimelineEnabled, globalTimelineYear])

  const [layersLoaded, setLayersLoaded] = useState<Record<string, boolean>>({})
  const [isLoadingLayers, setIsLoadingLayers] = useState<Record<string, boolean>>({})
  const {
    stars: starsRef, isManualZoom, isWheelZoom, wheelCursorLatLng, justEnteredMapbox,
    mapboxBaseZoom: mapboxBaseZoomRef, isAutoRotating: isAutoRotatingRef, manualRotation: manualRotationRef,
    loading: loadingRef, shaderMaterials: shaderMaterialsRef, ledDotMaterial: ledDotMaterialRef,
    layersReadyCalled: layersReadyCalledRef, cameraAnimation: cameraAnimationRef, animationId: animationIdRef,
    zoom: zoomRef, highlightGlows: highlightGlowsRef, listHighlightedSites: listHighlightedSitesRef,
    listHighlightedPositions: listHighlightedPositionsRef, proximityRaycaster: proximityRaycasterRef,
    lastHoverCallbackTime, lastHoverCoords, baseColors: baseColorsRef, sitePositions3D: sitePositions3DRef,
    validSites: validSitesRef, hoverCenter: hoverCenterRef,
  } = refs
  const HOVER_THROTTLE_MS = 100

  const {
    isHoveringList: isHoveringListRef, isContributePickerActive: isContributePickerActiveRef,
    onContributeMapConfirm: onContributeMapConfirmRef, onSiteSelect: onSiteSelectRef,
    frontLineLayers: frontLineLayersRef, backLineLayers: backLineLayersRef,
    paleoshorelineLines: paleoshorelineLinesRef, paleoshorelinePositionsCache: paleoshorelinePositionsCacheRef,
    paleoshorelineLoadId: paleoshorelineLoadIdRef, fadeManager: fadeManagerRef,
    geoLabels: geoLabelsRef, allLabelMeshes: allLabelMeshesRef, cuddleOffsets: cuddleOffsetsRef,
    cuddleAnimations: cuddleAnimationsRef, isPageVisible: isPageVisibleRef, webglContextLost: webglContextLostRef,
    needsLabelReload: needsLabelReloadRef, layerLabels: layerLabelsRef, geoLabelsVisible: geoLabelsVisibleRef,
    labelTypesVisible: labelTypesVisibleRef, vectorLayers: vectorLayersRef,
    updateGeoLabels: updateGeoLabelsRef, updateEmpireLabelsVisibility: updateEmpireLabelsVisibilityRef,
    updateMeasurementLabelsVisibility: updateMeasurementLabelsVisibilityRef, labelUpdateThrottle: labelUpdateThrottleRef,
    visibleLabelNames: visibleLabelNamesRef, visibleAfterCollision: visibleAfterCollisionRef,
    lastCalculatedZoom: lastCalculatedZoomRef, labelVisibilityState: labelVisibilityStateRef,
    basemapMesh: basemapMeshRef, basemapSectionMeshes, basemapBackMesh: basemapBackMeshRef,
    proximityCircle: proximityCircleRef, proximityCenter: proximityCenterRef, proximityPreview: proximityPreviewRef,
    proximityPreviewCenter: proximityPreviewCenterRef, proximityCircleCenterPos: proximityCircleCenterPosRef,
    backLayersLoaded: backLayersLoadedRef,
  } = refs

  // Sync refs with current values
  showTooltipsRef.current = showTooltips
  showEmpireLabelsRef.current = showEmpireLabels
  showAncientCitiesRef.current = showAncientCities
  visibleEmpiresRef.current = visibleEmpires
  isHoveringListRef.current = isHoveringList ?? false
  isContributePickerActiveRef.current = isContributeMapPickerActive ?? false
  onContributeMapConfirmRef.current = onContributeMapConfirm
  onSiteSelectRef.current = onSiteSelect
  geoLabelsVisibleRef.current = geoLabelsVisible
  labelTypesVisibleRef.current = labelTypesVisible
  vectorLayersRef.current = vectorLayers


  // Fast color update during proximity hover - no React state, direct BufferGeometry update
  const updateProximityColors = useCallback((centerLng: number | null, centerLat: number | null, radius: number) => {
    if (!sceneRef.current?.points || !baseColorsRef.current || !sitePositions3DRef.current) return

    const geometry = sceneRef.current.points.geometry
    const colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute
    const colors = colorAttr.array as Float32Array
    const baseColors = baseColorsRef.current
    const positions = sitePositions3DRef.current

    // Also update backPoints if they exist
    const backGeometry = sceneRef.current.backPoints?.geometry
    const backColorAttr = backGeometry?.getAttribute('color') as THREE.BufferAttribute | undefined
    const backColors = backColorAttr?.array as Float32Array | undefined

    if (centerLng === null || centerLat === null) {
      // No center - restore all to full brightness
      for (let i = 0; i < colors.length; i++) {
        colors[i] = baseColors[i]
        if (backColors) backColors[i] = baseColors[i]
      }
    } else {
      // Convert center to 3D position
      const phi = (90 - centerLat) * Math.PI / 180
      const theta = (centerLng + 180) * Math.PI / 180
      const cx = -Math.sin(phi) * Math.cos(theta)
      const cy = Math.cos(phi)
      const cz = Math.sin(phi) * Math.sin(theta)

      // Convert radius (km) to angular distance threshold
      // Earth radius ≈ 6371 km, so angle = radius / 6371 radians
      // For 3D distance on unit sphere: d = 2 * sin(angle/2)
      const angularDist = radius / 6371
      const threshold3D = 2 * Math.sin(angularDist / 2)
      const thresholdSq = threshold3D * threshold3D

      const numSites = positions.length / 3
      for (let i = 0; i < numSites; i++) {
        const px = positions[i * 3]
        const py = positions[i * 3 + 1]
        const pz = positions[i * 3 + 2]

        // Squared 3D distance (avoid sqrt for performance)
        const dx = px - cx
        const dy = py - cy
        const dz = pz - cz
        const distSq = dx * dx + dy * dy + dz * dz

        // Dimming for dots outside proximity (0.65 = 65% brightness)
        const fadeFactor = distSq <= thresholdSq ? 1.0 : 0.65

        colors[i * 3] = baseColors[i * 3] * fadeFactor
        colors[i * 3 + 1] = baseColors[i * 3 + 1] * fadeFactor
        colors[i * 3 + 2] = baseColors[i * 3 + 2] * fadeFactor
        if (backColors) {
          backColors[i * 3] = baseColors[i * 3] * fadeFactor
          backColors[i * 3 + 1] = baseColors[i * 3 + 1] * fadeFactor
          backColors[i * 3 + 2] = baseColors[i * 3 + 2] * fadeFactor
        }
      }
    }

    colorAttr.needsUpdate = true
    if (backColorAttr) backColorAttr.needsUpdate = true
  }, [])

  // ===========================================================================
  // MAIN THREE.JS EFFECT - Scene Setup, Animation Loop, and Event Handlers
  // This effect manages the entire Three.js lifecycle:
  //   1. SCENE SETUP (lines ~1445-1965): Renderer, scene, camera, globe, basemap, stars
  //   2. ANIMATION LOOP (lines ~1972-2373): Frame-by-frame rendering and updates
  //   3. EVENT HANDLERS (lines ~2376-2715): Resize, wheel, mouse interactions
  //   4. CLEANUP (lines ~2716-2730): Dispose of Three.js resources
  // ===========================================================================
  useEffect(() => {
    if (!containerRef.current) return

    // Scene setup
    const sceneOptions: SceneInitOptions = {
      initialPosition,
      refs: {
        webglContextLostRef,
        needsLabelReloadRef,
        isPageVisibleRef,
        warpProgressRef,
        warpTargetCameraPosRef,
        warpInitialCameraPosRef,
        basemapMeshRef,
        basemapBackMeshRef,
        basemapSectionMeshes,
        shaderMaterialsRef,
        starsRef,
        logoSpriteRef,
        logoMaterialRef,
        logoAnimationStartedRef,
        labelGroupRef,
        splashDoneRef,
      },
      setGpuName,
      setSoftwareRendering,
      setSceneReady,
    }

    const sceneResult = initializeScene(containerRef.current, sceneOptions)
    const {
      renderer,
      scene,
      camera,
      controls,
      globe,
      basemapMesh: _basemapMesh,
      basemapMaterial: _basemapMaterial,
      basemapBackMesh: _basemapBackMesh,
      basemapBackMaterial: _basemapBackMaterial,
      sectionMeshes: _sectionMeshes,
      starsGroup,
      starMaterial: _starMaterial,
      labelGroup: _labelGroup,
      minDist,
      maxDist,
      rotationSpeed,
      lastFrameTime: initialLastFrameTime,
      handleVisibilityChange,
      isCleanedUp,
    } = sceneResult
    sceneRef.current = { renderer, scene, camera, controls, points: null, backPoints: null, shadowPoints: null, globe }

    // Animation loop context
    const animationCtx: AnimationLoopContext = {
      renderer, scene, camera, controls, globe, starsGroup, minDist, maxDist, rotationSpeed,
      lastFrameTime: { value: initialLastFrameTime },
      frames: { value: 0 },
      fpsLastTime: { value: performance.now() },
      animationId: animationIdRef.current,
      _cameraDir: new THREE.Vector3(),
      _centerPoint: new THREE.Vector3(),
      _right: new THREE.Vector3(),
      _up: new THREE.Vector3(0, 1, 0),
      _p1: new THREE.Vector3(),
      _p2: new THREE.Vector3(),
      _p1Screen: new THREE.Vector3(),
      _p2Screen: new THREE.Vector3(),

      isPageVisibleRef, webglContextLostRef, fpsRef, lowFpsStartTimeRef,
      warpProgressRef, warpLinearProgressRef, warpStartTimeRef,
      warpCompleteForLabelsRef, warpInitialCameraPosRef, warpTargetCameraPosRef,
      layersReadyCalledRef, dotsAnimationCompleteRef, logoAnimationStartedRef,
      logoSpriteRef, logoMaterialRef, basemapMeshRef, basemapBackMeshRef,
      basemapSectionMeshes, shaderMaterialsRef, selectedDotMaterialRef,
      dotSizeRef, isAutoRotatingRef, isHoveringListRef, manualRotationRef,
      backgroundLoadingCompleteRef, showMapboxRef, mapboxServiceRef,
      mapboxTransitioningRef, satelliteModeRef, isManualZoom, splashDoneRef,
      starsRef, updateEmpireLabelsVisibilityRef, updateMeasurementLabelsVisibilityRef,
      lastScaleUpdateRef, kmPerPixelRef, listHighlightedSitesRef, showTooltipsRef,
      listHighlightedPositionsRef, highlightFrozenRef, frozenSiteRef,
      frozenTooltipPosRef, highlightGlowsRef, measurementLabelsRef,
      measurementMarkersRef, proximityCenterRef, lastMousePosRef,
      sitePositions3DRef, validSitesRef, lastHoverCheckRef, currentHoveredSiteRef,
      lastMoveTimeRef, lastSeenSiteRef, isFrozenRef, frozenAtRef,
      firstFreezeCompleteRef, sitesPassedDuringFreezeRef, lastSiteIdRef,
      isHoveringTooltipRef, allLabelMeshesRef, geoLabelsVisibleRef,
      geoLabelsRef, layerLabelsRef, fadeManagerRef, labelVisibilityStateRef,
      visibleAfterCollisionRef, cuddleOffsetsRef, cuddleAnimationsRef,
      setLowFps, setZoom, setScaleBar, setListHighlightedPositions,
      setTooltipSiteOnFront, setTooltipPos, setHoveredSite, setIsFrozen, setFrozenSite,
    }
    runAnimationLoop(animationCtx)

    // Event handlers
    const sceneObjects: EventHandlerSceneObjects = {
      renderer, camera, controls, globe, minDist, maxDist
    }

    const handlerRefs: EventHandlerRefs = {
      containerRef, mapboxServiceRef, showMapboxRef, sitesRef,
      lastMousePosRef, lastMoveTimeRef, lastCoordsUpdateRef,
      currentHoveredSiteRef, isFrozenRef, frozenSiteRef, hoveredSiteRef,
      highlightFrozenRef, cameraAnimationRef, onSiteSelectRef,
      isContributePickerActiveRef, onContributeMapConfirmRef,
      measureModeRef, onMeasurePointAddRef, measureSnapEnabledRef,
      measurementsRef, currentMeasurePointsRef, zoomRef
    }

    const handlerSetters: EventHandlerSetters = {
      setZoom, setCursorCoords, setTooltipPos,
      setHoveredSite, setIsFrozen, setFrozenSite
    }

    const handlerCallbacks: EventHandlerCallbacks = {
      onProximitySet,
      isLoading
    }
    const { cleanup: cleanupEventHandlers } = setupEventHandlers(
      sceneObjects, handlerRefs, handlerSetters, handlerCallbacks, isManualZoom
    )

    // Cleanup
    return () => {
      isCleanedUp.value = true
      cancelAnimationFrame(animationIdRef.current.value)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      cleanupEventHandlers()
      renderer.dispose()
      containerRef.current?.removeChild(renderer.domElement)
      logoSpriteRef.current = null
      logoMaterialRef.current = null
      logoAnimationStartedRef.current = false
      warpStartTimeRef.current = null
      warpProgressRef.current = 0
      warpLinearProgressRef.current = 0
      warpCompleteForLabelsRef.current = false
      cuddleAnimationsRef.current.forEach(id => cancelAnimationFrame(id))
      cuddleAnimationsRef.current.clear()
    }
  }, [])

  // Mapbox initialization
  useEffect(() => {
    const deps: MapboxInitEffectDeps = {
      mapboxContainerRef,
      mapboxServiceRef,
    }
    return createMapboxInitEffect(deps)
  }, [])

  const labelsLoadedRef = refs.labelsLoaded
  const [labelsLoaded, setLabelsLoaded] = useState(false)
  const labelsLoadingRef = refs.labelsLoading

  useLayersReady({
    refs,
    labelsLoaded,
    texturesReady,
    layersLoaded,
    onLayersReady,
  })
  const [labelReloadTrigger, setLabelReloadTrigger] = useState(0)
  const totalLabelsCountRef = refs.totalLabelsCount
  // Reserved: skipped labels for on-demand loading when user enables them
  // const skippedLabelsRef = useRef<GeoLabel[]>([])
  // const skippedLabelsLoadedTypesRef = useRef<Set<string>>(new Set())

  // Zoom ref for geo label system (defined earlier with other refs)
  zoomRef.current = zoom

  // Build context for geo label system functions
  const buildGeoLabelContext = useCallback((): GeoLabelContext => ({
    sceneRef,
    labelsLoadedRef,
    labelsLoadingRef,
    totalLabelsCountRef,
    geoLabelsRef,
    allLabelMeshesRef,
    layerLabelsRef,
    geoLabelsVisibleRef,
    labelTypesVisibleRef,
    vectorLayersRef,
    visibleLabelNamesRef,
    visibleAfterCollisionRef,
    labelVisibilityStateRef,
    lastCalculatedZoomRef,
    fadeManagerRef,
    cuddleOffsetsRef,
    zoomRef,
    kmPerPixelRef,
    empireLabelsRef,
    visibleEmpiresRef,
    showEmpireLabelsRef,
    ancientCitiesRef,
    ancientCitiesDataRef,
    showAncientCitiesRef,
    updateGeoLabelsRef,
    setLabelsLoaded,
    needsLabelReloadRef,
    setLabelReloadTrigger,
  }), [setLabelsLoaded, setLabelReloadTrigger])

  // Load labels during initial loading screen
  useEffect(() => {
    if (!sceneReady || labelsLoadedRef.current || labelsLoadingRef.current || !sceneRef.current) return

    labelsLoadingRef.current = true

    const loadLabels = async () => {
      await loadGeoLabelsImpl(buildGeoLabelContext())
    }

    loadLabels().catch((err) => {
      console.error('[Loading] Labels error:', err)
      labelsLoadingRef.current = false
    })
  }, [sceneReady, labelReloadTrigger, buildGeoLabelContext])

  // Handle WebGL context restoration - reload labels when textures are lost
  useEffect(() => {
    const handleLabelReload = () => {
      handleLabelReloadImpl(buildGeoLabelContext())
    }

    window.addEventListener('webgl-labels-need-reload', handleLabelReload)
    return () => window.removeEventListener('webgl-labels-need-reload', handleLabelReload)
  }, [buildGeoLabelContext])

  // When user enables labels, just show them (already preloaded)
  useEffect(() => {
    if (geoLabelsVisible && labelsLoadedRef.current) updateGeoLabelsRef.current?.()
  }, [geoLabelsVisible])

  // Update geographic label visibility based on zoom and camera direction
  const updateGeoLabels = useCallback(() => {
    updateGeoLabelsImpl(buildGeoLabelContext())
  }, [buildGeoLabelContext])

  // Store callback ref for animation loop
  updateGeoLabelsRef.current = updateGeoLabels

  // Empire labels visibility function (called from animation loop)
  // Backside hiding is handled by the shader's vViewFade - we only manage toggle/empire visibility here
  // This function is stored in a ref so it can be updated by HMR without recreating the animation loop
  const updateEmpireLabelsVisibility = useCallback((cameraDir: THREE.Vector3) => {
    updateEmpireLabelsVisibilityImpl(cameraDir, {
      sceneRef,
      fadeManagerRef,
      labelVisibilityStateRef,
      empireLabelsRef,
      showEmpireLabelsRef,
      visibleEmpiresRef,
      ancientCitiesRef,
      showAncientCitiesRef,
      regionLabelsRef,
    })
  }, [])

  // Store callback ref for animation loop (updates on every render so HMR works)
  updateEmpireLabelsVisibilityRef.current = updateEmpireLabelsVisibility

  // Measurement labels visibility function (for animation loop via ref)
  updateMeasurementLabelsVisibilityRef.current = (cameraDir: THREE.Vector3, hideBackside: number = 0) => {
    // For perspective camera, horizon is at dotProduct = R/D where R=1 (globe radius) and D=camera distance
    // At typical zoom, camera is ~2.5-4 units away, so horizon is around 0.25-0.4
    // Use 0.25 as threshold - hide when label is at or past the visible edge
    const horizonThreshold = 0.25
    const fadeStart = horizonThreshold + 0.15 // Start fading slightly before horizon
    const isSatellite = satelliteModeRef.current

    // Helper to calculate opacity for labels (hidden on back side)
    const calcLabelOpacity = (dotProduct: number): number => {
      if (dotProduct > fadeStart) return 1.0
      if (dotProduct > horizonThreshold) return (dotProduct - horizonThreshold) / (fadeStart - horizonThreshold)
      return 0
    }

    // Helper to calculate opacity for lines/markers
    // Smoothly blend between dimmed (30%) and hidden based on hideBackside value
    const calcDimOpacity = (dotProduct: number): number => {
      if (dotProduct > fadeStart) return 1.0
      if (dotProduct > horizonThreshold) {
        const fadeProgress = (dotProduct - horizonThreshold) / (fadeStart - horizonThreshold)
        // Blend between dimmed and hidden based on hideBackside (0-1)
        const dimmedOpacity = 0.3 + 0.7 * fadeProgress
        const hiddenOpacity = fadeProgress
        const blendFactor = isSatellite ? 1 : hideBackside
        return dimmedOpacity * (1 - blendFactor) + hiddenOpacity * blendFactor
      }
      // Backside: blend between 30% (dimmed) and 0% (hidden)
      const blendFactor = isSatellite ? 1 : hideBackside
      return 0.3 * (1 - blendFactor)
    }

    // Update labels - hide on back side
    for (const entry of measurementLabelsRef.current) {
      if (!entry || !entry.label || !entry.midpoint) continue
      const { label, midpoint } = entry
      const labelDir = midpoint.clone().normalize()
      const dotProduct = cameraDir.dot(labelDir)
      const mat = label.material as THREE.SpriteMaterial
      const opacity = calcLabelOpacity(dotProduct)
      label.visible = opacity > 0
      mat.opacity = opacity
    }

    // Update markers (rings and squares)
    for (const entry of measurementMarkersRef.current) {
      if (!entry || !entry.marker || !entry.position) continue
      const { marker, position } = entry
      const markerDir = position.clone().normalize()
      const dotProduct = cameraDir.dot(markerDir)
      const opacity = calcDimOpacity(dotProduct)
      marker.visible = opacity > 0
      // Update material opacity if it has one
      if ((marker as any).material) {
        const mat = (marker as any).material
        if (mat.opacity !== undefined) {
          mat.opacity = opacity
        }
      }
    }

    // Update lines
    for (const entry of measurementLinesRef.current) {
      if (!entry || !entry.line || !entry.points || entry.points.length === 0) continue
      const { line, points } = entry
      // Use the middle point of the arc for visibility check
      const midIndex = Math.floor(points.length / 2)
      const midPoint = points[midIndex]
      const lineDir = midPoint.clone().normalize()
      const dotProduct = cameraDir.dot(lineDir)
      const opacity = calcDimOpacity(dotProduct)
      line.visible = opacity > 0
      const mat = line.material as THREE.LineBasicMaterial
      mat.opacity = opacity
    }

    // Update proximity circle visibility (only hide in satellite mode)
    if (isSatellite && proximityCircleCenterPosRef.current) {
      const centerDir = proximityCircleCenterPosRef.current.clone().normalize()
      const dotProduct = cameraDir.dot(centerDir)
      const opacity = calcDimOpacity(dotProduct)

      // Update proximity circle group
      if (proximityCircleRef.current) {
        proximityCircleRef.current.visible = opacity > 0
        // Update materials in the group
        proximityCircleRef.current.traverse((child) => {
          if ((child as any).material) {
            const mat = (child as any).material
            if (mat.opacity !== undefined) {
              // Preserve relative opacity (fill is much more transparent than outline)
              const baseOpacity = mat === (proximityCircleRef.current?.children[0] as any)?.material ? 0.048 : 0.8
              mat.opacity = baseOpacity * opacity
            }
          }
        })
      }

      // Update center marker
      if (proximityCenterRef.current) {
        proximityCenterRef.current.visible = opacity > 0
        const mat = proximityCenterRef.current.material as THREE.SpriteMaterial
        mat.opacity = opacity
      }
    }
  }

  // Call updateGeoLabels when zoom/visibility/detail/type toggles/layer visibility/empire visibility change
  // Debounced to 500ms - only update when zooming has stopped
  useEffect(() => {
    // Clear any pending debounced update
    if (labelUpdateThrottleRef.current) {
      clearTimeout(labelUpdateThrottleRef.current)
    }

    // Schedule update after 500ms of no changes
    labelUpdateThrottleRef.current = setTimeout(() => {
      updateGeoLabels()
      labelUpdateThrottleRef.current = null
    }, 500)

    // Cleanup on unmount or before next effect
    return () => {
      if (labelUpdateThrottleRef.current) {
        clearTimeout(labelUpdateThrottleRef.current)
      }
    }
  }, [zoom, geoLabelsVisible, labelTypesVisible, vectorLayers, updateGeoLabels, showEmpireLabels, visibleEmpires])

  // Update points (delegated to extracted sitesRenderer module)
  useEffect(() => {
    if (!sceneRef.current) return
    const { scene, globe } = sceneRef.current
    sitesRef.current = sites

    // Clean up old points using helper function
    cleanupPoints(sceneRef.current.points, shaderMaterialsRef.current)
    sceneRef.current.points = null
    cleanupPoints(sceneRef.current.backPoints, shaderMaterialsRef.current)
    sceneRef.current.backPoints = null
    cleanupPoints(sceneRef.current.shadowPoints, shaderMaterialsRef.current)
    sceneRef.current.shadowPoints = null
    cleanupPoints(selectedPointsRef.current, shaderMaterialsRef.current)
    selectedPointsRef.current = null

    // If no sites, clear refs and return
    if (!sites.length) {
      validSitesRef.current = []
      sitePositions3DRef.current = null
      setHoveredSite(null)
      return
    }

    // Create site points using extracted module
    const options: SitesRendererOptions = {
      sites,
      filterMode,
      sourceColors: sourceColors || {},
      countryColors: countryColors || {},
      dotSize,
      contextIsOffline,
      cachedSourceIds,
      searchWithinProximity,
      proximityCenter: proximity?.center,
      isSatelliteMode: tileLayers.satellite,
      dotsAnimationComplete: dotsAnimationCompleteRef.current,
    }

    const result = createSitePoints(options)

    if (!result) {
      validSitesRef.current = []
      sitePositions3DRef.current = null
      setHoveredSite(null)
      return
    }

    // Store refs for fast color updates during hover
    baseColorsRef.current = result.baseColors
    sitePositions3DRef.current = result.positions3D
    validSitesRef.current = result.validSites

    // Store materials for size updates
    ledDotMaterialRef.current = [result.frontMaterial, result.backMaterial] as any

    // Register materials for camera updates
    shaderMaterialsRef.current.push(result.backMaterial)
    shaderMaterialsRef.current.push(result.frontMaterial)
    shaderMaterialsRef.current.push(result.shadowMaterial)

    // Add points to globe
    const parent = globe || scene
    parent.add(result.backPoints)
    parent.add(result.shadowPoints)
    parent.add(result.frontPoints)

    // Store in sceneRef for satellite mode toggle
    sceneRef.current.backPoints = result.backPoints
    sceneRef.current.shadowPoints = result.shadowPoints
    sceneRef.current.points = result.frontPoints

    // Handle selected points overlay
    if (result.selectedPoints && result.selectedMaterial) {
      shaderMaterialsRef.current.push(result.selectedMaterial)
      selectedDotMaterialRef.current = result.selectedMaterial
      parent.add(result.selectedPoints)
      selectedPointsRef.current = result.selectedPoints
    } else {
      selectedDotMaterialRef.current = null
    }
  }, [sites, filterMode, sourceColors, countryColors, dotSize, contextIsOffline, cachedSourceIds, searchWithinProximity, proximity?.center, tileLayers.satellite])

  // Sync dot size to Mapbox
  useEffect(() => {
    dotSizeRef.current = dotSize
    if (mapboxServiceRef.current) {
      mapboxServiceRef.current.setDotSize(dotSize)
    }
  }, [dotSize])

  // Render measurement lines, markers, and distance labels (delegated to extracted module)
  useEffect(() => {
    if (!sceneRef.current) return
    const { globe } = sceneRef.current

    const ctx: MeasurementRendererContext = {
      globe,
      measurementObjectsRef,
      measurementLabelsRef,
      measurementLinesRef,
      measurementMarkersRef,
    }

    renderMeasurements(ctx, {
      measurements,
      currentMeasurePoints,
      selectedMeasurementId,
      measureUnit,
      currentMeasurementColor,
    })
  }, [measurements, currentMeasurePoints, selectedMeasurementId, measureUnit, dotSize, currentMeasurementColor])

  // Random mode: hide unselected dots when active (only show the random selected dot)
  useEffect(() => {
    if (!sceneRef.current) return
    const { points, backPoints, shadowPoints } = sceneRef.current

    // When randomModeActive, hide all unselected dots
    if (points) points.visible = !randomModeActive
    if (backPoints) backPoints.visible = !randomModeActive
    if (shadowPoints) shadowPoints.visible = !randomModeActive
  }, [randomModeActive])

  // Sync visible empires to parent for "Within empires" filtering
  // When global timeline is enabled, only include empires that exist at the current year
  useEffect(() => {
    if (globalTimelineEnabled) {
      const effectivelyVisible = new Set<string>()
      visibleEmpires.forEach(empireId => {
        const empire = EMPIRES.find(e => e.id === empireId)
        if (empire && globalTimelineYear >= empire.startYear && globalTimelineYear <= empire.endYear) {
          effectivelyVisible.add(empireId)
        }
      })
      onVisibleEmpiresChange?.(effectivelyVisible)
    } else {
      onVisibleEmpiresChange?.(visibleEmpires)
    }
  }, [visibleEmpires, globalTimelineEnabled, globalTimelineYear, onVisibleEmpiresChange])

  // Sync empire years to parent for "Within empires" filtering
  // Note: This is now called AFTER polygon data loads (in loadEmpireBordersForYear)
  // to prevent flash of all dots while new year's polygon data is loading
  const onEmpireYearsChangeRef = refs.onEmpireYearsChange
  onEmpireYearsChangeRef.current = onEmpireYearsChange

  // Draw proximity circle on the globe
  useEffect(() => {
    if (!sceneRef.current) return

    const { globe } = sceneRef.current

    // Remove existing circle and center
    if (proximityCircleRef.current) {
      globe.remove(proximityCircleRef.current)
      disposeGroup(proximityCircleRef.current)
      proximityCircleRef.current = null
    }
    if (proximityCenterRef.current) {
      globe.remove(proximityCenterRef.current)
      disposeSprite(proximityCenterRef.current)
      proximityCenterRef.current = null
    }

    // Draw new circle if proximity is set
    if (proximity?.center) {
      const [centerLng, centerLat] = proximity.center
      const { circle, centerPoint } = createProximityCircle(centerLng, centerLat, proximity.radius)
      globe.add(circle)
      proximityCircleRef.current = circle
      proximityCircleCenterPosRef.current = centerPoint.clone() // Store for back-side visibility

      // Add center marker
      const marker = createCenterMarker(centerPoint)
      globe.add(marker)
      proximityCenterRef.current = marker

      // Apply dimming to dots outside the proximity ring
      updateProximityColors(centerLng, centerLat, proximity.radius)
    } else {
      proximityCircleCenterPosRef.current = null
      // Reset dimming when proximity is cleared
      updateProximityColors(null, null, proximity?.radius || 500)
    }
  }, [proximity?.center, proximity?.radius, updateProximityColors])

  // Preview circle on mouse hover when in "Set on Globe" mode
  useEffect(() => {
    if (!sceneRef.current || !containerRef.current) return
    if (!proximity?.isSettingOnGlobe) {
      // Clean up preview when exiting set mode
      if (proximityPreviewRef.current) {
        sceneRef.current.globe.remove(proximityPreviewRef.current)
        disposeGroup(proximityPreviewRef.current)
        proximityPreviewRef.current = null
      }
      if (proximityPreviewCenterRef.current) {
        sceneRef.current.globe.remove(proximityPreviewCenterRef.current)
        disposeSprite(proximityPreviewCenterRef.current)
        proximityPreviewCenterRef.current = null
      }
      // Reset hover center and restore colors if there's no set proximity
      if (hoverCenterRef.current && !proximity?.center) {
        hoverCenterRef.current = null
        updateProximityColors(null, null, proximity?.radius || 500)
      }
      return
    }

    const { globe, camera } = sceneRef.current
    const container = containerRef.current

    const handleMouseMove = (e: MouseEvent) => {
      const mouseX = (e.clientX / window.innerWidth) * 2 - 1
      const mouseY = -(e.clientY / window.innerHeight) * 2 + 1

      // Reuse raycaster for performance
      if (!proximityRaycasterRef.current) {
        proximityRaycasterRef.current = new THREE.Raycaster()
      }
      const raycaster = proximityRaycasterRef.current
      raycaster.setFromCamera(new THREE.Vector2(mouseX, mouseY), camera)
      const hits = raycaster.intersectObject(globe, false)

      // Remove old preview
      if (proximityPreviewRef.current) {
        globe.remove(proximityPreviewRef.current)
        disposeGroup(proximityPreviewRef.current)
        proximityPreviewRef.current = null
      }
      if (proximityPreviewCenterRef.current) {
        globe.remove(proximityPreviewCenterRef.current)
        disposeSprite(proximityPreviewCenterRef.current)
        proximityPreviewCenterRef.current = null
      }

      if (hits.length > 0) {
        const point = hits[0].point.normalize()
        const lat = 90 - Math.acos(point.y) * 180 / Math.PI
        const lng = Math.atan2(point.z, -point.x) * 180 / Math.PI - 180

        // Update colors directly (fast, no React state) - always update for smooth visuals
        hoverCenterRef.current = [lng, lat]
        updateProximityColors(lng, lat, proximity.radius)

        // Throttle parent callback (for coord display in FilterPanel only)
        const now = performance.now()
        if (now - lastHoverCallbackTime.current >= HOVER_THROTTLE_MS) {
          const lastCoords = lastHoverCoords.current
          if (!lastCoords || Math.abs(lastCoords[0] - lng) > 0.1 || Math.abs(lastCoords[1] - lat) > 0.1) {
            onProximityHover?.([lng, lat])
            lastHoverCoords.current = [lng, lat]
            lastHoverCallbackTime.current = now
          }
        }

        // Create preview circle with lower opacity
        const { circle, centerPoint } = createProximityCircle(lng, lat, proximity.radius, 0.5)
        globe.add(circle)
        proximityPreviewRef.current = circle

        // Create preview center marker
        const marker = createCenterMarker(centerPoint, 0.7)
        globe.add(marker)
        proximityPreviewCenterRef.current = marker
      } else {
        // Not on globe - restore colors if no set proximity
        if (hoverCenterRef.current) {
          hoverCenterRef.current = null
          if (!proximity?.center) {
            updateProximityColors(null, null, proximity.radius)
          } else {
            // Restore to set center
            updateProximityColors(proximity.center[0], proximity.center[1], proximity.radius)
          }
        }
        if (lastHoverCoords.current !== null) {
          onProximityHover?.(null)
          lastHoverCoords.current = null
        }
      }
    }

    const handleMouseLeave = () => {
      // Restore colors when mouse leaves
      if (hoverCenterRef.current) {
        hoverCenterRef.current = null
        if (!proximity?.center) {
          updateProximityColors(null, null, proximity?.radius || 500)
        } else {
          updateProximityColors(proximity.center[0], proximity.center[1], proximity?.radius || 500)
        }
      }
      if (lastHoverCoords.current !== null) {
        onProximityHover?.(null)
        lastHoverCoords.current = null
      }
    }

    container.addEventListener('mousemove', handleMouseMove)
    container.addEventListener('mouseleave', handleMouseLeave)
    return () => {
      container.removeEventListener('mousemove', handleMouseMove)
      container.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [proximity?.isSettingOnGlobe, proximity?.radius, proximity?.center, onProximityHover, updateProximityColors])

  // Helper function to convert lat/lng to 3D
  const latLngTo3DRef = useCallback((lat: number, lng: number, r: number) => {
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180
    return new THREE.Vector3(
      -r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi),
      r * Math.sin(phi) * Math.sin(theta)
    )
  }, [])

  // Build context for vector renderer functions
  const buildVectorRendererContext = useCallback((): VectorRendererContext => ({
    sceneRef,
    loadingRef,
    shaderMaterialsRef,
    frontLineLayersRef,
    backLineLayersRef,
    backLayersLoadedRef,
    fadeManagerRef,
    detailLevelRef,
    layerLabelsRef,
    allLabelMeshesRef,
    updateGeoLabelsRef,
    vectorLayers,
    tileLayers,
    setIsLoadingLayers,
    setLayersLoaded,
    latLngTo3DRef,
  }), [vectorLayers, tileLayers, latLngTo3DRef])

  // Load FRONT layer (always high detail, visible on front of globe)
  const loadFrontLayer = useCallback(async (layerKey: VectorLayerKey) => {
    return loadFrontLayerImpl(layerKey, buildVectorRendererContext())
  }, [vectorLayers, latLngTo3DRef, tileLayers.satellite])

  // Reload rivers/lakes when detail level changes (track previous to avoid initial load)
  const prevDetailLevelRef = refs.prevDetailLevel
  useEffect(() => {
    if (!sceneRef.current) return

    // Skip initial mount - the visibility effect handles first load
    if (prevDetailLevelRef.current === null) {
      prevDetailLevelRef.current = detailLevel
      return
    }

    // Only reload if detail level actually changed
    if (prevDetailLevelRef.current !== detailLevel) {
      prevDetailLevelRef.current = detailLevel

      // Reload LOD-enabled layers that are currently visible
      if (vectorLayers.rivers) {
        loadFrontLayer('rivers')
      }
      if (vectorLayers.lakes) {
        loadFrontLayer('lakes')
      }
    }
  }, [detailLevel, loadFrontLayer, vectorLayers.rivers, vectorLayers.lakes])

  // Load BACK layer (same LOD as front, visible on back of globe)
  const loadBackLayer = useCallback(async (layerKey: VectorLayerKey, forceReload = false) => {
    return loadBackLayerImpl(layerKey, buildVectorRendererContext(), forceReload)
  }, [vectorLayers, latLngTo3DRef, tileLayers.satellite])

  // Reload BACK layers when detail level changes (mirrors front layer LOD effect)
  const prevBackDetailLevelRef = refs.prevBackDetailLevel
  useEffect(() => {
    if (!sceneRef.current) return

    // Skip initial mount
    if (prevBackDetailLevelRef.current === null) {
      prevBackDetailLevelRef.current = detailLevel
      return
    }

    // Only reload if detail level actually changed
    if (prevBackDetailLevelRef.current !== detailLevel) {
      prevBackDetailLevelRef.current = detailLevel

      // Reload LOD-enabled back layers that are currently loaded
      if (backLayersLoadedRef.current['rivers'] && vectorLayers.rivers) {
        loadBackLayer('rivers', true) // forceReload = true
      }
      if (backLayersLoadedRef.current['lakes'] && vectorLayers.lakes) {
        loadBackLayer('lakes', true)
      }
    }
  }, [detailLevel, loadBackLayer, vectorLayers.rivers, vectorLayers.lakes])

  // Load paleoshoreline contour for current sea level (delegated to extracted module)
  const loadPaleoshoreline = useCallback(async (level: number) => {
    const ctx: PaleoshorelineContext = {
      sceneRef: sceneRef as React.MutableRefObject<{ globe: THREE.Mesh; camera: THREE.PerspectiveCamera } | null>,
      shaderMaterialsRef,
      paleoshorelineLinesRef,
      paleoshorelinePositionsCacheRef,
      paleoshorelineLoadIdRef,
      fadeManagerRef,
      latLngTo3D: latLngTo3DRef,
      setIsLoadingPaleoshoreline: paleo.setIsLoadingPaleoshoreline,
      replaceCoastlines,
    }
    return loadPaleoshorelineImpl(level, ctx)
  }, [latLngTo3DRef, replaceCoastlines, paleo.setIsLoadingPaleoshoreline])

  // Build GlobeRenderContext for extracted empire renderer functions
  const buildEmpireRenderContext = useCallback((): GlobeRenderContext => ({
    sceneRef,
    shaderMaterialsRef,
    empireBorderLinesRef,
    empireLabelsRef,
    regionLabelsRef,
    ancientCitiesRef,
    allLabelMeshesRef,
    labelVisibilityStateRef,
    fadeManagerRef,
    regionDataRef,
    ancientCitiesDataRef,
    empirePolygonFeaturesRef,
    empireLoadAbortRef,
    visibleEmpiresRef,
    satelliteModeRef,
    empireYearsRef,
    onEmpireYearsChangeRef,
    updateGeoLabelsRef,
    empireLabelPositionDebounceRef,
    showEmpireLabelsRef,
    showAncientCitiesRef,
    latLngTo3D: latLngTo3DRef,
    showEmpireLabels,
    showAncientCities,
    empireYearOptions,
    onEmpirePolygonsLoaded,
    setLoadingEmpires,
    setEmpireYearOptions,
    setEmpireCentroids,
    setEmpireDefaultYears,
    setEmpireYears,
    setLoadedEmpires,
    loadedEmpires,
  }), [
    latLngTo3DRef, showEmpireLabels, showAncientCities, empireYearOptions,
    onEmpirePolygonsLoaded, setLoadingEmpires, setEmpireYearOptions,
    setEmpireCentroids, setEmpireDefaultYears, setEmpireYears, setLoadedEmpires,
    loadedEmpires
  ])
  // Load empire metadata and default year boundaries
  const loadEmpireBorders = useCallback(async (empireId: string) => {
    const ctx = buildEmpireRenderContext()
    return loadEmpireBordersImpl(empireId, ctx)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildEmpireRenderContext])

  // SIMPLE: Remove ALL objects tagged with empireId from globe - no cache, just scan and remove
  const removeEmpireFromGlobe = useCallback((empireId: string) => {
    const ctx = buildEmpireRenderContext()
    removeEmpireFromGlobeImpl(empireId, ctx)
  }, [buildEmpireRenderContext])

  // SIMPLE: Load empire borders for a year - fetch new, add to scene, then remove old (prevents flickering)
  const loadEmpireBordersForYear = useCallback(async (
    empireId: string,
    year: number,
    color: number,
    createLabel: boolean = false,
    yearOptions?: number[]
  ) => {
    const ctx = buildEmpireRenderContext()
    return loadEmpireBordersForYearImpl(empireId, year, color, createLabel, ctx, yearOptions)
  }, [buildEmpireRenderContext])

  // Update empire label text only (without changing position) - used during slider interaction
  const updateEmpireLabelText = useCallback((empireId: string, name: string, startYear?: number, endYear?: number, currentYear?: number, yearOptionsParam?: number[]) => {
    const ctx = buildEmpireRenderContext()
    updateEmpireLabelTextImpl(empireId, name, startYear, endYear, currentYear, ctx, yearOptionsParam)
  }, [buildEmpireRenderContext])

  // Animate empire label position smoothly to new location
  const animateEmpireLabelPosition = useCallback((empireId: string, targetLat: number, targetLng: number, duration: number = 500) => {
    const ctx = buildEmpireRenderContext()
    animateEmpireLabelPositionImpl(empireId, targetLat, targetLng, ctx, duration)
  }, [buildEmpireRenderContext])

  // Load and display region labels for an empire
  const loadRegionLabels = useCallback(async (empireId: string, year: number) => {
    const ctx = buildEmpireRenderContext()
    return loadRegionLabelsImpl(empireId, year, ctx)
  }, [buildEmpireRenderContext])

  // Remove region labels for an empire
  const removeRegionLabels = useCallback((empireId: string) => {
    const ctx = buildEmpireRenderContext()
    removeRegionLabelsImpl(empireId, ctx)
  }, [buildEmpireRenderContext])

  // Load and display ancient cities for an empire (robust with cancellation support)
  const loadAncientCities = useCallback(async (empireId: string, year: number) => {
    const ctx = buildEmpireRenderContext()
    return loadAncientCitiesImpl(empireId, year, ctx)
  }, [buildEmpireRenderContext])

  // Remove ancient cities for an empire (aborts pending loads, idempotent)
  const removeAncientCities = useCallback((empireId: string) => {
    const ctx = buildEmpireRenderContext()
    removeAncientCitiesImpl(empireId, ctx)
  }, [buildEmpireRenderContext])

  // Age sync effect - syncs age slider from empire start to current slider position
  useEffect(() => {
    if (empiresWithAgeSync.size === 0 || !onAgeRangeSync) return

    const syncedEmpires = EMPIRES.filter(e =>
      visibleEmpires.has(e.id) && empiresWithAgeSync.has(e.id)
    )

    if (syncedEmpires.length === 0) return

    // Collect start years and current slider positions
    const startYears: number[] = []
    const currentYears: number[] = []

    for (const empire of syncedEmpires) {
      startYears.push(empire.startYear)

      const currentYear = empireYears[empire.id] ?? empire.startYear
      const yearOptions = empireYearOptions[empire.id]

      if (yearOptions && yearOptions.length > 0) {
        const currentIndex = yearOptions.indexOf(currentYear)
        // Get the end of the current period (next year option, or same year if at end)
        const nextYear = currentIndex < yearOptions.length - 1
          ? yearOptions[currentIndex + 1]
          : currentYear
        currentYears.push(nextYear)
      } else {
        currentYears.push(currentYear)
      }
    }

    // Range: earliest empire start to latest current slider position
    const minYear = Math.min(...startYears)
    const maxYear = Math.max(...currentYears)

    // Call parent to update age slider
    onAgeRangeSync([minYear, maxYear])
  }, [visibleEmpires, empiresWithAgeSync, empireYears, empireYearOptions, onAgeRangeSync])

  // Toggle empire visibility
  const toggleEmpire = (id: string) => {
    const empire = EMPIRES.find(e => e.id === id)
    setVisibleEmpires(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        // Also remove age sync when hiding
        setEmpiresWithAgeSync(p => {
          const n = new Set(p)
          n.delete(id)
          // Reset age slider when no empires are synced
          if (n.size === 0 && onAgeRangeSync) {
            onAgeRangeSync([-5000, 1500])
          }
          return n
        })
        // Clear all empire geometry
        removeEmpireFromGlobe(id)
        setLoadedEmpires(prev => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
        // Fade out empire label
        const label = empireLabelsRef.current[id]
        if (label) {
          fadeLabelOut(label, fadeManagerRef.current, `empire-label-${id}`)
        }
        // Remove ancient cities
        removeAncientCities(id)
        // Remove region labels
        removeRegionLabels(id)
      } else {
        next.add(id)
        loadEmpireBorders(id)  // Load if not already loaded (will add geometry to scene)
        // Load cities and region labels for current year
        const currentYear = empireYears[id]
        if (currentYear !== undefined && empire) {
          loadAncientCities(id, currentYear)
          loadRegionLabels(id, currentYear)
        }
        // Fade in empire label
        const label = empireLabelsRef.current[id]
        if (label && showEmpireLabels) {
          fadeLabelIn(label, fadeManagerRef.current, `empire-label-${id}`)
        }
      }
      return next
    })
  }

  // Change empire year (for temporal slider)
  const changeEmpireYear = useCallback(async (empireId: string, year: number) => {
    const empire = EMPIRES.find(e => e.id === empireId)
    if (!empire) return

    setEmpireYears(prev => ({ ...prev, [empireId]: year }))

    // Load boundaries for the new year
    await loadEmpireBordersForYear(empireId, year, empire.color, false)

    // Update label text immediately (without changing position)
    updateEmpireLabelText(empireId, empire.name, empire.startYear, empire.endYear, year)

    // Debounce label position update - only move after 1 second of no changes
    if (empireLabelPositionDebounceRef.current[empireId]) {
      clearTimeout(empireLabelPositionDebounceRef.current[empireId])
    }
    empireLabelPositionDebounceRef.current[empireId] = setTimeout(() => {
      const centroids = empireCentroids[empireId]
      if (centroids && centroids[String(year)]) {
        const [lat, lng] = centroids[String(year)]
        // Animate label to new position instead of recreating
        animateEmpireLabelPosition(empireId, lat, lng, 600)
      }
    }, 1000)

    // Update ancient cities for the new year
    loadAncientCities(empireId, year)

    // Update region labels for the new year
    loadRegionLabels(empireId, year)
  }, [empireCentroids, loadEmpireBordersForYear, updateEmpireLabelText, animateEmpireLabelPosition, loadAncientCities, loadRegionLabels])

  // Selection button handlers for Empire Borders window
  const handleSelectAllEmpires = () => {
    EMPIRES.forEach(empire => {
      if (!visibleEmpires.has(empire.id)) {
        toggleEmpire(empire.id)
      }
    })
  }

  const handleSelectNoEmpires = () => {
    visibleEmpires.forEach(empireId => {
      toggleEmpire(empireId)
    })
  }

  const handleSelectInvertEmpires = () => {
    EMPIRES.forEach(empire => {
      toggleEmpire(empire.id)
    })
  }

  // Global timeline change handler - updates all visible empires to show appropriate year
  const handleGlobalTimelineChange = useCallback((year: number) => {
    setGlobalTimelineYear(year)
    // Update each visible empire to show the appropriate year
    visibleEmpires.forEach(empireId => {
      const empire = EMPIRES.find(e => e.id === empireId)
      if (!empire) return

      const existsAtYear = year >= empire.startYear && year <= empire.endYear

      // Hide/show border lines
      const lines = empireBorderLinesRef.current[empireId]
      if (lines) {
        lines.forEach(line => { line.visible = existsAtYear })
      }

      // Hide/show fills and back lines (traverse scene for objects with this empireId)
      sceneRef.current?.scene.traverse((obj) => {
        if (obj.userData.empireId === empireId) {
          // For back lines (renderOrder < 0), also check satellite mode
          if (obj.renderOrder < 0) {
            obj.visible = existsAtYear && !satelliteModeRef.current
          } else {
            obj.visible = existsAtYear
          }
        }
      })

      // Hide/show empire label
      const label = empireLabelsRef.current[empireId]
      if (label && showEmpireLabelsRef.current) {
        label.visible = existsAtYear
      }

      // Hide/show region labels
      const regionLabels = regionLabelsRef.current[empireId]
      if (regionLabels && showEmpireLabelsRef.current) {
        regionLabels.forEach(rl => { rl.visible = existsAtYear })
      }

      // Hide/show ancient cities
      const cities = ancientCitiesRef.current[empireId]
      if (cities && showAncientCitiesRef.current) {
        cities.forEach(city => { city.visible = existsAtYear })
      }

      // If empire exists at this year, update to closest available year
      if (existsAtYear) {
        const options = empireYearOptions[empireId] || []
        if (options.length > 0) {
          const closestYear = options.reduce((prev, curr) =>
            Math.abs(curr - year) < Math.abs(prev - year) ? curr : prev
          , options[0])
          if (closestYear !== undefined && closestYear !== empireYears[empireId]) {
            changeEmpireYear(empireId, closestYear)
          }
        }
      }
    })
  }, [visibleEmpires, empireYearOptions, empireYears, changeEmpireYear])


  // Track previous values to detect actual changes
  const prevSeaLevel = refs.prevSeaLevel
  const prevReplaceCoastlines = refs.prevReplaceCoastlines
  const prevPaleoshorelineVisible = refs.prevPaleoshorelineVisible

  // Single effect to handle all paleoshoreline state changes
  useEffect(() => {
    const seaLevelChanged = prevSeaLevel.current !== seaLevel
    const replaceChanged = prevReplaceCoastlines.current !== replaceCoastlines
    const visibilityChanged = prevPaleoshorelineVisible.current !== paleoshorelineVisible

    // Update refs
    prevSeaLevel.current = seaLevel
    prevReplaceCoastlines.current = replaceCoastlines
    prevPaleoshorelineVisible.current = paleoshorelineVisible

    // Handle visibility off - fade out then dispose (delegated to extracted module)
    if (!paleoshorelineVisible) {
      disposePaleoshoreline(
        paleoshorelineLinesRef,
        sceneRef as React.MutableRefObject<{ globe: THREE.Mesh } | null>,
        fadeManagerRef
      )
      return
    }

    // Handle replaceCoastlines toggle - update coastlines visibility
    if (replaceChanged) {
      if (replaceCoastlines) {
        coastlinesWereActive.current = vectorLayers.coastlines
        setVectorLayers(prev => ({ ...prev, coastlines: false }))
      } else {
        if (coastlinesWereActive.current) {
          setVectorLayers(prev => ({ ...prev, coastlines: true }))
        }
      }
    }

    // Load/reload paleoshoreline when needed (always high detail)
    if (paleoshorelineVisible && (seaLevelChanged || replaceChanged || visibilityChanged)) {
      loadPaleoshoreline(seaLevel)
    }
  }, [seaLevel, replaceCoastlines, paleoshorelineVisible, loadPaleoshoreline, vectorLayers.coastlines])

  // Load layers when visibility changes (always high detail)
  // NOTE: This runs in parallel with texture and label loading
  useEffect(() => {
    Object.keys(vectorLayers).forEach(key => {
      const layerKey = key as VectorLayerKey
      const isEnabled = vectorLayers[layerKey]
      const isLoaded = layersLoaded[layerKey]
      const isLoading = isLoadingLayers[layerKey]

      if (isEnabled && !isLoaded && !isLoading) {
        console.log(`[Loading] Starting ${layerKey} load...`)
        // Load back layer (low detail for performance) if not already loaded
        if (!backLayersLoadedRef.current[layerKey]) {
          loadBackLayer(layerKey)
        }
        // Load front layer (high detail)
        loadFrontLayer(layerKey)
      }
    })
  }, [vectorLayers, layersLoaded, isLoadingLayers, loadFrontLayer, loadBackLayer])

  // Handle layer visibility changes with fade animation (unified)
  useEffect(() => {
    if (!sceneRef.current) return
    const fm = fadeManagerRef.current

    Object.keys(LAYER_CONFIG).forEach(key => {
      const layerKey = key as VectorLayerKey
      const visible = vectorLayers[layerKey]

      // Handle front and back layers separately (they have different materials)
      const frontLines = frontLineLayersRef.current[layerKey] || []
      const backLines = backLineLayersRef.current[layerKey] || []

      // Front layer materials (de-duplicate since all lines share one material)
      if (frontLines.length > 0) {
        const frontMaterial = frontLines[0].material as THREE.Material
        if (visible) {
          frontLines.forEach(l => l.visible = true)
          fm.fadeTo(layerKey, [frontMaterial], 1)
        } else {
          fm.fadeTo(layerKey, [frontMaterial], 0, {
            onComplete: () => frontLines.forEach(l => l.visible = false)
          })
        }
      }

      // Back layer materials (separate key to avoid conflicts)
      // Don't show back lines in satellite mode (satellite is opaque)
      if (backLines.length > 0) {
        const backMaterial = backLines[0].material as THREE.Material
        if (visible && !tileLayers.satellite) {
          backLines.forEach(l => l.visible = true)
          fm.fadeTo(`${layerKey}_back`, [backMaterial], 1)
        } else {
          fm.fadeTo(`${layerKey}_back`, [backMaterial], 0, {
            onComplete: () => backLines.forEach(l => l.visible = false)
          })
        }
      }
    })
  }, [vectorLayers, tileLayers.satellite])

  // Auto-switch between Three.js and Mapbox based on zoom level (66% threshold)
  useEffect(() => {
    const deps: AutoSwitchEffectDeps = {
      zoom,
      showMapbox,
      setShowMapbox,
      mapboxServiceRef,
      justEnteredMapbox,
      contextIsOffline,
      hasMapboxTilesCached,
      setShowMapboxOfflineWarning,
    }
    createAutoSwitchEffect(deps)
  }, [zoom, showMapbox, contextIsOffline, hasMapboxTilesCached])

  // Sync showMapbox state to ref for animation loop and handle mode switching
  // When showMapbox is true: Mapbox becomes the PRIMARY interactive view
  // Three.js state is frozen and restored when switching back
  useEffect(() => {
    const deps: ModeSwitchEffectDeps = {
      showMapbox,
      onSiteClick,
      prevShowMapboxRef,
      showMapboxRef,
      mapboxServiceRef,
      sceneRef,
      mapboxTransitioningRef,
      mapboxBaseZoomRef,
      justEnteredMapbox,
      zoomRef,
      isManualZoom,
      isWheelZoom,
      wheelCursorLatLng,
      containerRef,
      measureModeRef,
      measureSnapEnabledRef,
      measurementsRef,
      currentMeasurePointsRef,
      sitesRef,
      siteClickJustHappenedRef,
      onSiteSelectRef,
      onMeasurePointAddRef,
      showTooltipsRef,
      isFrozenRef,
      frozenSiteRef,
      currentHoveredSiteRef,
      lastSeenSiteRef,
      highlightFrozenRef,
      lastMousePosRef,
      lastMoveTimeRef,
      isHoveringTooltipRef,
      lastCoordsUpdateRef,
      listHighlightedSitesRef,
      listHighlightedPositionsRef,
      setHoveredSite,
      setFrozenSite,
      setIsFrozen,
      setTooltipPos,
      setCursorCoords,
      setZoom,
      setListHighlightedSites,
      setListHighlightedPositions,
      onProximitySet,
    }
    createModeSwitchEffect(deps)
  }, [showMapbox, onSiteClick])

  // Update Mapbox sites when sites or color mode changes (separate from mode switching)
  useEffect(() => {
    const deps: SitesSyncEffectDeps = {
      showMapbox,
      sites,
      filterMode,
      sourceColors,
      countryColors,
      searchWithinProximity,
      mapboxServiceRef,
    }
    createSitesSyncEffect(deps)
  }, [showMapbox, sites, filterMode, sourceColors, countryColors, searchWithinProximity])

  // Sync measurements to Mapbox when in Mapbox mode
  useEffect(() => {
    const deps: MeasurementsSyncEffectDeps = {
      showMapbox,
      measurements,
      currentMeasurePoints,
      measureUnit,
      mapboxServiceRef,
    }
    createMeasurementsSyncEffect(deps)
  }, [showMapbox, measurements, currentMeasurePoints, measureUnit])

  // Sync proximity circle to Mapbox when in Mapbox mode
  useEffect(() => {
    const deps: ProximityCircleSyncEffectDeps = {
      showMapbox,
      proximity,
      mapboxServiceRef,
    }
    createProximityCircleSyncEffect(deps)
  }, [showMapbox, proximity?.center, proximity?.radius])

  // Sync selected sites (green rings) to Mapbox when in Mapbox mode
  useEffect(() => {
    const deps: SelectedSitesSyncEffectDeps = {
      showMapbox,
      listFrozenSiteIds,
      sitesRef,
      mapboxServiceRef,
    }
    createSelectedSitesSyncEffect(deps)
  }, [showMapbox, listFrozenSiteIds])

  // Cleanup FadeManager on unmount
  useEffect(() => {
    return () => fadeManagerRef.current.dispose()
  }, [])

  // Background preload vector layers (rivers, lakes) for instant toggle
  const vectorPreloadedRef = refs.vectorPreloaded

  useEffect(() => {
    // Skip preloading in offline mode - we only use cached data
    if (vectorPreloadedRef.current || !sceneRef.current || OfflineFetch.isOffline) return
    vectorPreloadedRef.current = true

    const preloadVectorLayers = async () => {
      // Preload vector layers (rivers, lakes) - coastlines and borders load by default
      const vectorLayersToPreload: VectorLayerKey[] = ['rivers', 'lakes']
      for (const layerKey of vectorLayersToPreload) {
        try {
          const url = getLayerUrl(layerKey, 'high')
          await offlineFetch(url).then(r => r.json())
        } catch (e) {
          // Silently ignore preload failures
        }
      }
    }

    // Start preloading after a short delay to not compete with initial render
    const timeoutId = setTimeout(preloadVectorLayers, 2000)
    return () => clearTimeout(timeoutId)
  }, [])

  return (
    <div className={`globe-wrapper ${!hudVisible ? 'hud-hidden' : ''}`} style={{ '--hud-scale': hudScale } as React.CSSProperties}>
      {/* Hardware acceleration warning banner */}
      <HardwareWarning
        softwareRendering={softwareRendering}
        warningDismissed={warningDismissed}
        onDismiss={() => setWarningDismissed(true)}
        gpuName={gpuName}
      />
      {/* Mapbox GL container - rendered behind Three.js canvas */}
      <div ref={mapboxContainerRef} className="mapbox-globe-container" />
      <div ref={containerRef} className="globe-container" data-measure-mode={measureMode ? 'true' : undefined} />

      {/* Mapbox offline warning banner */}
      <MapboxOfflineWarning
        visible={showMapboxOfflineWarning}
        onDownload={onOfflineClick}
        onDismiss={() => setShowMapboxOfflineWarning(false)}
      />

      {/* Tooltips - hover and selected sites */}
      <TooltipOverlay
        showTooltips={showTooltips}
        isFrozen={isFrozen}
        frozenSite={frozenSite}
        hoveredSite={hoveredSite}
        tooltipPos={tooltipPos}
        tooltipSiteOnFront={tooltipSiteOnFront}
        showMapbox={showMapbox}
        listFrozenSiteIds={listFrozenSiteIds}
        onTooltipMouseEnter={handleTooltipMouseEnter}
        onTooltipMouseLeave={handleTooltipMouseLeave}
        onTooltipClick={onTooltipClick}
        onSiteClick={onSiteClick}
        listHighlightedSites={listHighlightedSites}
        listHighlightedPositions={listHighlightedPositions}
      />

      {/* Coordinates display - fixed position top center */}
      <CoordinateDisplay coords={cursorCoords} visible={showCoordinates} />

      {/* Contribute picker instruction - below coordinates */}
      <ContributePickerHint active={isContributeMapPickerActive ?? false} onCancel={onContributeMapCancel} />

      {/* Scale bar - fixed position bottom center */}
      <ScaleBar scaleBar={scaleBar} visible={showScale} />

      {/* Social + Contribute - positioned top right */}
      <SocialLinks
        onContributeClick={onContributeClick}
        isContributeMapPickerActive={isContributeMapPickerActive}
        onAIAgentClick={onAIAgentClick}
      />

      {/* FPS and options panel */}
      <OptionsPanel
        ref={fpsRef}
        showTooltips={showTooltips}
        onToggleTooltips={ui.toggleTooltips}
        showCoordinates={showCoordinates}
        onToggleCoordinates={ui.toggleCoordinates}
        showScale={showScale}
        onToggleScale={ui.toggleScale}
        hudScale={hudScale}
        hudScalePreview={hudScalePreview}
        onHudScaleChange={ui.setHudScale}
        onHudScalePreviewChange={ui.setHudScalePreview}
        dotSize={dotSize}
        onDotSizeChange={ui.setDotSize}
        onHideHud={ui.hideHud}
        onScreenshot={handleScreenshot}
        canUndoSelection={canUndoSelection}
        onUndoSelection={onUndoSelection}
        canRedoSelection={canRedoSelection}
        onRedoSelection={onRedoSelection}
        sceneReady={sceneReady}
        backgroundLoadingComplete={backgroundLoadingComplete}
        labelsLoaded={labelsLoaded}
        isOffline={isOffline}
        onOfflineClick={onOfflineClick}
        dataSourceIndicator={dataSourceIndicator}
        onDisclaimerClick={onDisclaimerClick}
        gpuName={gpuName}
        lowFps={lowFps}
        lowFpsReady={lowFpsReady}
      />

      {/* Vertical zoom slider */}
      <ZoomControls
        zoom={zoom}
        setZoom={setZoom}
        isPlaying={isPlaying}
        onTogglePlay={toggle}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
      />

      {/* Layer toggle panel */}
      <MapLayersPanel
        minimized={mapLayersMinimized}
        onToggleMinimize={() => setMapLayersMinimized(prev => !prev)}
        tileLayers={tileLayers}
        onTileLayerToggle={(layer) => setTileLayers(prev => ({
          satellite: layer === 'satellite' ? !prev.satellite : false,
          streets: layer === 'streets' ? !prev.streets : false
        }))}
        vectorLayers={vectorLayers}
        onVectorLayerToggle={(key) => setVectorLayers(prev => ({ ...prev, [key]: !prev[key] }))}
        isLoadingLayers={isLoadingLayers}
        geoLabelsVisible={geoLabelsVisible}
        onGeoLabelsToggle={labels.toggleGeoLabels}
        labelTypesExpanded={labelTypesExpanded}
        onLabelTypesExpandToggle={labels.toggleLabelTypesExpanded}
        labelTypesVisible={labelTypesVisible}
        onLabelTypeToggle={labels.toggleLabelType}
        showMapbox={showMapbox}
        isOffline={contextIsOffline}
        cachedLayerIds={cachedLayerIds}
      >
        {/* Historical Layers Section - nested inside MapLayersPanel */}
        <HistoricalLayersSection
          paleoshorelineVisible={paleoshorelineVisible}
          onPaleoshorelineToggle={paleo.togglePaleoshoreline}
          isLoadingPaleoshoreline={isLoadingPaleoshoreline}
          seaLevel={seaLevel}
          sliderSeaLevel={sliderSeaLevel}
          onSeaLevelChange={paleo.setSeaLevel}
          onSliderSeaLevelChange={paleo.setSliderSeaLevel}
          replaceCoastlines={replaceCoastlines}
          onReplaceCoastlinesChange={paleo.setReplaceCoastlines}
          empireBordersWindowOpen={empireBordersWindowOpen}
          hasVisibleEmpires={visibleEmpires.size > 0}
          onEmpireBordersToggle={() => setEmpireBordersWindowOpen(prev => !prev)}
          showMapbox={showMapbox}
        />
      </MapLayersPanel>

      {/* Empire Borders Window */}
      <EmpireBordersPanel
        isOpen={empireBordersWindowOpen}
        onClose={() => setEmpireBordersWindowOpen(false)}
        height={empireBordersHeight}
        onHeightChange={setEmpireBordersHeight}
        visibleEmpires={visibleEmpires}
        onToggleEmpire={toggleEmpire}
        loadingEmpires={loadingEmpires}
        empireYears={empireYears}
        empireYearOptions={empireYearOptions}
        empireDefaultYears={empireDefaultYears}
        onChangeEmpireYear={(empireId, year) => {
          // Debounce the actual border loading
          if (empireYearDebounceRef.current[empireId]) {
            clearTimeout(empireYearDebounceRef.current[empireId])
          }
          empireYearDebounceRef.current[empireId] = setTimeout(() => {
            changeEmpireYear(empireId, year)
          }, 50)
        }}
        onUpdateEmpireYearDisplay={(empireId, year) => {
          setEmpireYears(prev => ({ ...prev, [empireId]: year }))
          const empire = EMPIRES.find(e => e.id === empireId)
          if (empire) {
            updateEmpireLabelText(empireId, empire.name, empire.startYear, empire.endYear, year, empireYearOptions[empireId])
          }
        }}
        onEmpireYearSliderInput={(empireId, year) => {
          setEmpireYears(prev => ({ ...prev, [empireId]: year }))
          const empire = EMPIRES.find(e => e.id === empireId)
          if (empire) {
            updateEmpireLabelText(empireId, empire.name, empire.startYear, empire.endYear, year, empireYearOptions[empireId])
          }
        }}
        expandedRegions={expandedRegions}
        onToggleRegion={(region) => {
          setExpandedRegions(prev => {
            const next = new Set(prev)
            next.has(region) ? next.delete(region) : next.add(region)
            return next
          })
        }}
        showEmpireLabels={showEmpireLabels}
        onToggleEmpireLabels={(show) => {
          setShowEmpireLabels(show)
          showEmpireLabelsRef.current = show
          // Toggle visibility of all empire labels
          Object.values(empireLabelsRef.current).forEach(label => {
            label.visible = show && visibleEmpires.has((label.userData as { empireId?: string })?.empireId ?? '')
          })
          // Toggle visibility of region labels
          Object.entries(regionLabelsRef.current).forEach(([empireId, labels]) => {
            labels.forEach(label => {
              label.visible = show && visibleEmpires.has(empireId)
            })
          })
          // Toggle visibility of ancient city labels
          Object.entries(ancientCitiesRef.current).forEach(([empireId, cities]) => {
            cities.forEach(city => {
              city.visible = show && visibleEmpires.has(empireId)
            })
          })
        }}
        showAncientCities={showAncientCities}
        onToggleAncientCities={(show) => {
          setShowAncientCities(show)
          showAncientCitiesRef.current = show
          // Toggle visibility of all city markers
          Object.entries(ancientCitiesRef.current).forEach(([empireId, cities]) => {
            cities.forEach(city => {
              city.visible = show && visibleEmpires.has(empireId)
            })
          })
        }}
        globalTimelineEnabled={globalTimelineEnabled}
        onToggleGlobalTimeline={(enabled) => {
          setGlobalTimelineEnabled(enabled)
          if (enabled) {
            handleGlobalTimelineChange(globalTimelineYear)
          }
        }}
        globalTimelineYear={globalTimelineYear}
        globalTimelineRange={globalTimelineRange}
        onGlobalTimelineYearChange={handleGlobalTimelineChange}
        onGlobalTimelineYearInput={(year) => {
          setGlobalTimelineYear(year)
          // Throttle expensive updates to every 50ms
          const now = Date.now()
          if (now - globalTimelineThrottleRef.current >= 50) {
            globalTimelineThrottleRef.current = now
            handleGlobalTimelineChange(year)
          }
        }}
        onSelectAll={handleSelectAllEmpires}
        onSelectNone={handleSelectNoEmpires}
        onSelectInvert={handleSelectInvertEmpires}
      />

      {/* Screenshot mode overlay - visible when HUD is hidden */}
      {!hudVisible && (
        <ScreenshotControls
          onScreenshot={handleScreenshot}
          onShowHud={ui.showHud}
        />
      )}
    </div>
  )
}
