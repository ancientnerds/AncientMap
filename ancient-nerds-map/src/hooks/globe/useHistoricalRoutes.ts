/**
 * useHistoricalRoutes - Historical route visibility and panel state
 */

import { useState, useRef } from 'react'

export function useHistoricalRoutes() {
  const [routesPanelOpen, setRoutesPanelOpen] = useState(false)
  const [routesPanelHeight, setRoutesPanelHeight] = useState(350)
  const [routesPanelWidth, setRoutesPanelWidth] = useState(280)
  const [routesPanelPosition, setRoutesPanelPosition] = useState({ x: window.innerWidth - 600, y: 200 })
  const [visibleRoutes, setVisibleRoutes] = useState<Set<string>>(new Set())
  const visibleRoutesRef = useRef<Set<string>>(new Set())
  const [loadingRoutes, setLoadingRoutes] = useState<Set<string>>(new Set())
  const [expandedRouteGroups, setExpandedRouteGroups] = useState<Set<string>>(new Set(['Ancient Trade Routes']))

  visibleRoutesRef.current = visibleRoutes

  return {
    routesPanelOpen, setRoutesPanelOpen,
    routesPanelHeight, setRoutesPanelHeight,
    routesPanelWidth, setRoutesPanelWidth,
    routesPanelPosition, setRoutesPanelPosition,
    visibleRoutes, setVisibleRoutes, visibleRoutesRef,
    loadingRoutes, setLoadingRoutes,
    expandedRouteGroups, setExpandedRouteGroups,
  }
}
