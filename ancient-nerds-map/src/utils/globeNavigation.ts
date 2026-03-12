let globeWindow: Window | null = null

export function navigateGlobeToSite(siteId: string) {
  if (globeWindow && !globeWindow.closed) {
    globeWindow.postMessage({ type: 'focus-site', siteId }, window.location.origin)
    globeWindow.focus()
    return
  }
  globeWindow = window.open(`/globe.html?focus=${siteId}`, 'ancient-nerds-globe')
}

export function navigateGlobeToCoords(lat: number, lon: number, activateProximity = false) {
  if (globeWindow && !globeWindow.closed) {
    globeWindow.postMessage({ type: 'fly-to-coords', lat, lon, activateProximity }, window.location.origin)
    globeWindow.focus()
    return
  }
  const params = `lat=${lat}&lon=${lon}${activateProximity ? '&proximity=1' : ''}`
  globeWindow = window.open(`/globe.html?${params}`, 'ancient-nerds-globe')
}
