/**
 * SSR-Einstieg. Bekommt das Route-Payload, liefert head und body-HTML.
 *
 * Die Komposition ist exakt die des Rendertests (seo/__tests__/render.test.tsx):
 * AuthProvider gehört in den Baum, weil ResearchPaperPage und ArticlesPage
 * über useIsFounder() → useAuth() ohne Provider werfen. Bewusst KEIN
 * OfflineProvider — kein serverseitig erreichbarer Zweig konsumiert
 * useOffline(), der Rendertest beweist das.
 *
 * Kein Fallback bei unbekanntem Typ: ein Tippfehler im Payload muss laut
 * scheitern, nicht eine leere Seite ausliefern.
 */

import { renderToString } from 'react-dom/server'

import { AuthProvider } from './contexts/AuthContext'
import { renderHead } from './seo/meta'
import { SeoRoute, registry } from './seo/registry'
import { RouteProvider } from './seo/RouteContext'
import type { AnRoute } from './types/anRoute'

export function render(route: AnRoute): { head: string; html: string } {
  const entry = registry[route.type]
  if (!entry) throw new Error(`unknown route type: ${route.type}`)
  const html = renderToString(
    <RouteProvider value={route}>
      <AuthProvider>
        <SeoRoute />
      </AuthProvider>
    </RouteProvider>,
  )
  return { head: renderHead(entry.meta(route as never)), html }
}
