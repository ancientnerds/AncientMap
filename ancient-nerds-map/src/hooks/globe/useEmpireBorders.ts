/**
 * useEmpireBorders - Empire loading, labels, regions, and cities
 * Manages historical empire border visualization state
 */

import { useState, useCallback, useRef } from 'react'
import type * as THREE from 'three'
import { EMPIRES } from '../../config/empireData'
import type { GlobeLabelMesh } from '../../utils/LabelRenderer'

interface UseEmpireBordersOptions {
  // Callbacks for state changes that Globe.tsx needs to respond to
  onAgeRangeSync?: (range: [number, number]) => void
  onVisibleEmpiresChange?: (empireIds: Set<string>) => void
  onEmpireYearsChange?: (years: Record<string, number>) => void
  onEmpirePolygonsLoaded?: (empireId: string, year: number, features: any[]) => void

  // Rendering callbacks - called when empire needs to be rendered/updated
  onLoadEmpire?: (empireId: string, year: number) => Promise<void>
  onUnloadEmpire?: (empireId: string) => void
  onUpdateEmpireYear?: (empireId: string, year: number) => Promise<void>
  onUpdateLabelsVisibility?: (empireId: string, visible: boolean) => void
  onUpdateCitiesVisibility?: (empireId: string, visible: boolean) => void
}

export function useEmpireBorders(options: UseEmpireBordersOptions = {}) {
  const {
    onAgeRangeSync,
    onVisibleEmpiresChange,
    onEmpireYearsChange,
    onEmpirePolygonsLoaded: _onEmpirePolygonsLoaded,  // Reserved for future polygon loading callback
    onLoadEmpire,
    onUnloadEmpire,
    onUpdateEmpireYear,
    onUpdateLabelsVisibility,
    onUpdateCitiesVisibility,
  } = options

  // Empire visibility
  const [visibleEmpires, setVisibleEmpires] = useState<Set<string>>(new Set())
  const visibleEmpiresRef = useRef<Set<string>>(new Set())

  // Age sync
  const [empiresWithAgeSync, setEmpiresWithAgeSync] = useState<Set<string>>(new Set())

  // Loading state
  const [loadingEmpires, setLoadingEmpires] = useState<Set<string>>(new Set())
  const [loadedEmpires, setLoadedEmpires] = useState<Set<string>>(new Set())

  // Region expansion UI
  const [expandedRegions, setExpandedRegions] = useState<Set<string>>(new Set(['Mediterranean']))

  // Year controls
  const [empireYears, setEmpireYears] = useState<Record<string, number>>({})
  const empireYearsRef = useRef<Record<string, number>>({})
  const [empireYearOptions, setEmpireYearOptions] = useState<Record<string, number[]>>({})
  const [empireDefaultYears, setEmpireDefaultYears] = useState<Record<string, number>>({})
  const [empireCentroids, setEmpireCentroids] = useState<Record<string, Record<string, [number, number]>>>({})

  // Global timeline
  const [globalTimelineEnabled, setGlobalTimelineEnabled] = useState(false)
  const [globalTimelineYear, setGlobalTimelineYear] = useState(-500)

  // Labels toggle
  const [showEmpireLabels, setShowEmpireLabelsState] = useState(true)
  const showEmpireLabelsRef = useRef(true)

  // Cities toggle
  const [showAncientCities, setShowAncientCitiesState] = useState(true)
  const showAncientCitiesRef = useRef(true)

  // Wrapped setters that call callbacks
  const setShowEmpireLabels = useCallback((show: boolean | ((prev: boolean) => boolean)) => {
    setShowEmpireLabelsState(prev => {
      const newValue = typeof show === 'function' ? show(prev) : show
      showEmpireLabelsRef.current = newValue
      // Update visibility for all visible empires
      visibleEmpiresRef.current.forEach(empireId => {
        onUpdateLabelsVisibility?.(empireId, newValue)
      })
      return newValue
    })
  }, [onUpdateLabelsVisibility])

  const setShowAncientCities = useCallback((show: boolean | ((prev: boolean) => boolean)) => {
    setShowAncientCitiesState(prev => {
      const newValue = typeof show === 'function' ? show(prev) : show
      showAncientCitiesRef.current = newValue
      // Update visibility for all visible empires
      visibleEmpiresRef.current.forEach(empireId => {
        onUpdateCitiesVisibility?.(empireId, newValue)
      })
      return newValue
    })
  }, [onUpdateCitiesVisibility])

  // UI state
  const [empireBordersWindowOpen, setEmpireBordersWindowOpen] = useState(false)
  const [empireBordersHeight, setEmpireBordersHeight] = useState(300)

  // 3D object refs
  const empireBorderLinesRef = useRef<Record<string, THREE.Line[]>>({})
  const empireLabelsRef = useRef<Record<string, GlobeLabelMesh>>({})
  const regionLabelsRef = useRef<Record<string, GlobeLabelMesh[]>>({})
  const ancientCitiesRef = useRef<Record<string, GlobeLabelMesh[]>>({})

  // Data cache refs
  const regionDataRef = useRef<Record<string, Array<{ name: string; lat: number; lng: number; years: number[] }>> | null>(null)
  const ancientCitiesDataRef = useRef<Record<string, Array<{ name: string; lat: number; lng: number; years: number[]; type: string }>>>({})
  const empirePolygonFeaturesRef = useRef<Record<string, Array<{ geometry: { type: string; coordinates: any } }>>>({})

  // Abort controllers for cancellation
  const empireLoadAbortRef = useRef<Record<string, AbortController>>({})
  const empireYearDebounceRef = useRef<Record<string, NodeJS.Timeout>>({})
  const globalTimelineThrottleRef = useRef<number>(0)

  // Sync refs with state
  visibleEmpiresRef.current = visibleEmpires
  empireYearsRef.current = empireYears
  showEmpireLabelsRef.current = showEmpireLabels
  showAncientCitiesRef.current = showAncientCities

  // Calculate global timeline range from visible empires
  const globalTimelineRange = (() => {
    const enabledEmpires = EMPIRES.filter(e => visibleEmpires.has(e.id))
    if (enabledEmpires.length === 0) return { min: -3000, max: 1900 }
    return {
      min: Math.min(...enabledEmpires.map(e => e.startYear)),
      max: Math.max(...enabledEmpires.map(e => e.endYear))
    }
  })()

  // Toggle empire visibility
  const toggleEmpire = useCallback((empireId: string) => {
    setVisibleEmpires(prev => {
      const next = new Set(prev)
      const wasVisible = next.has(empireId)

      if (wasVisible) {
        next.delete(empireId)
        // Call unload callback when hiding
        onUnloadEmpire?.(empireId)
      } else {
        next.add(empireId)
        // Call load callback when showing
        const year = empireYearsRef.current[empireId] || empireDefaultYears[empireId]
        if (year !== undefined) {
          onLoadEmpire?.(empireId, year)
        }
      }
      onVisibleEmpiresChange?.(next)
      return next
    })
  }, [onVisibleEmpiresChange, onLoadEmpire, onUnloadEmpire, empireDefaultYears])

  // Toggle region expansion
  const toggleRegion = useCallback((region: string) => {
    setExpandedRegions(prev => {
      const next = new Set(prev)
      if (next.has(region)) {
        next.delete(region)
      } else {
        next.add(region)
      }
      return next
    })
  }, [])

  // Toggle age sync for an empire
  const toggleAgeSync = useCallback((empireId: string) => {
    setEmpiresWithAgeSync(prev => {
      const next = new Set(prev)
      if (next.has(empireId)) {
        next.delete(empireId)
      } else {
        next.add(empireId)
        // Sync age range when enabling
        const empire = EMPIRES.find(e => e.id === empireId)
        if (empire) {
          onAgeRangeSync?.([empire.startYear, empire.endYear])
        }
      }
      return next
    })
  }, [onAgeRangeSync])

  // Change empire year
  const changeEmpireYear = useCallback((empireId: string, year: number) => {
    setEmpireYears(prev => {
      const next = { ...prev, [empireId]: year }
      onEmpireYearsChange?.(next)
      // Call update callback if empire is visible
      if (visibleEmpiresRef.current.has(empireId)) {
        onUpdateEmpireYear?.(empireId, year)
      }
      return next
    })
  }, [onEmpireYearsChange, onUpdateEmpireYear])

  // Update empire year display (without triggering data load)
  const updateEmpireYearDisplay = useCallback((empireId: string, year: number) => {
    setEmpireYears(prev => ({ ...prev, [empireId]: year }))
  }, [])

  // Handle global timeline change
  const handleGlobalTimelineChange = useCallback((year: number) => {
    setGlobalTimelineYear(year)
    // Update all visible empires to appropriate year
    visibleEmpires.forEach(empireId => {
      const options = empireYearOptions[empireId]
      if (options && options.length > 0) {
        // Find the closest year <= globalYear
        const closestYear = options.reduce((prev, curr) => {
          if (curr <= year && curr > prev) return curr
          return prev
        }, options[0])
        changeEmpireYear(empireId, closestYear)
      }
    })
  }, [visibleEmpires, empireYearOptions, changeEmpireYear])

  // Select all empires
  const selectAllEmpires = useCallback(() => {
    const all = new Set(EMPIRES.map(e => e.id))
    setVisibleEmpires(all)
    onVisibleEmpiresChange?.(all)
  }, [onVisibleEmpiresChange])

  // Select no empires
  const selectNoEmpires = useCallback(() => {
    setVisibleEmpires(new Set())
    onVisibleEmpiresChange?.(new Set())
  }, [onVisibleEmpiresChange])

  // Invert empire selection
  const selectInvertEmpires = useCallback(() => {
    const inverted = new Set(EMPIRES.filter(e => !visibleEmpires.has(e.id)).map(e => e.id))
    setVisibleEmpires(inverted)
    onVisibleEmpiresChange?.(inverted)
  }, [visibleEmpires, onVisibleEmpiresChange])

  return {
    // Empire visibility
    visibleEmpires,
    setVisibleEmpires,
    visibleEmpiresRef,
    toggleEmpire,

    // Age sync
    empiresWithAgeSync,
    setEmpiresWithAgeSync,
    toggleAgeSync,

    // Loading state
    loadingEmpires,
    setLoadingEmpires,
    loadedEmpires,
    setLoadedEmpires,

    // Region expansion
    expandedRegions,
    setExpandedRegions,
    toggleRegion,

    // Year controls
    empireYears,
    setEmpireYears,
    empireYearsRef,
    empireYearOptions,
    setEmpireYearOptions,
    empireDefaultYears,
    setEmpireDefaultYears,
    empireCentroids,
    setEmpireCentroids,
    changeEmpireYear,
    updateEmpireYearDisplay,

    // Global timeline
    globalTimelineEnabled,
    setGlobalTimelineEnabled,
    globalTimelineYear,
    setGlobalTimelineYear,
    globalTimelineRange,
    handleGlobalTimelineChange,

    // Labels
    showEmpireLabels,
    setShowEmpireLabels,
    showEmpireLabelsRef,

    // Cities
    showAncientCities,
    setShowAncientCities,
    showAncientCitiesRef,

    // UI state
    empireBordersWindowOpen,
    setEmpireBordersWindowOpen,
    empireBordersHeight,
    setEmpireBordersHeight,

    // Quick actions
    selectAllEmpires,
    selectNoEmpires,
    selectInvertEmpires,

    // 3D object refs
    empireBorderLinesRef,
    empireLabelsRef,
    regionLabelsRef,
    ancientCitiesRef,

    // Data cache refs
    regionDataRef,
    ancientCitiesDataRef,
    empirePolygonFeaturesRef,

    // Abort/debounce refs
    empireLoadAbortRef,
    empireYearDebounceRef,
    globalTimelineThrottleRef
  }
}
