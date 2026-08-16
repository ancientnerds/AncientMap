/**
 * Das Route-Payload, das Server und Browser gemeinsam benutzen.
 *
 * Bis 2026-08-09 las jede Seite window.__AN_ROUTE__ direkt. Das ging nur im
 * Browser — serverseitiges Rendern fiel auf einen window.location-Zweig
 * zurück und stürzte ab. Über den Kontext bekommt der Server das Payload als
 * Prop, der Browser liest es beim Hydrieren einmal aus window.
 */

import { createContext, useContext, type ReactNode } from 'react'

import type { AnRoute } from '../types/anRoute'

declare global {
  interface Window {
    __AN_ROUTE__?: AnRoute
  }
}

const RouteCtx = createContext<AnRoute | undefined>(undefined)

export function RouteProvider({ value, children }: { value?: AnRoute; children: ReactNode }) {
  return <RouteCtx.Provider value={value}>{children}</RouteCtx.Provider>
}

export function useRoute(): AnRoute | undefined {
  return useContext(RouteCtx)
}

/** Nur im Browser-Einstieg aufrufen — liest das vom Server injizierte Payload. */
export function readInjectedRoute(): AnRoute | undefined {
  return typeof window === 'undefined' ? undefined : window.__AN_ROUTE__
}
