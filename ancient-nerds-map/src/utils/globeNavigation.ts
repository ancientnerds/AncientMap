let globeWindow: Window | null = null

export function navigateGlobeToSite(siteId: string) {
  if (globeWindow && !globeWindow.closed) {
    globeWindow.postMessage({ type: 'focus-site', siteId }, '*')
    globeWindow.focus()
    return
  }
  globeWindow = window.open(`/globe.html?focus=${siteId}`, 'ancient-nerds-globe')
}

export function navigateGlobeToCoords(lat: number, lon: number) {
  if (globeWindow && !globeWindow.closed) {
    globeWindow.postMessage({ type: 'fly-to-coords', lat, lon }, '*')
    globeWindow.focus()
    return
  }
  globeWindow = window.open(`/globe.html?lat=${lat}&lon=${lon}`, 'ancient-nerds-globe')
}
