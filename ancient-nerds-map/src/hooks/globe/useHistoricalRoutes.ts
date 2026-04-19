/**
 * useHistoricalRoutes - Historical route visibility and panel state
 */

import { useState, useRef } from 'react'

export function useHistoricalRoutes() {
  const [routesPanelOpen, setRoutesPanelOpen] = useState(false)
  const [routesPanelHeight, setRoutesPanelHeight] = useState(350)
  const [routesPanelPosition, setRoutesPanelPosition] = useState({ x: 0, y: 0 })
  const [visibleRoutes, setVisibleRoutes] = useState<Set<string>>(new Set())
  const visibleRoutesRef = useRef<Set<string>>(new Set())
  const [loadingRoutes, setLoadingRoutes] = useState<Set<string>>(new Set())
  const [expandedRouteGroups, setExpandedRouteGroups] = useState<Set<string>>(new Set(['Ancient Trade Routes']))

  visibleRoutesRef.current = visibleRoutes

  return {
    routesPanelOpen, setRoutesPanelOpen,
    routesPanelHeight, setRoutesPanelHeight,
    routesPanelPosition, setRoutesPanelPosition,
    visibleRoutes, setVisibleRoutes, visibleRoutesRef,
    loadingRoutes, setLoadingRoutes,
    expandedRouteGroups, setExpandedRouteGroups,
  }
}
