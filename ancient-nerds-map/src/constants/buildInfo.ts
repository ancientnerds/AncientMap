/**
 * Build identity — read from the document, never baked into a chunk.
 *
 * Der Commit-Hash steckte bis 2026-09-12 als `__BUILD_HASH__`-define direkt
 * in DataStore.ts (Cache-Buster `_v=`). DataStore importiert halb die App,
 * also bekam bei JEDEM Deploy ein Fünftel des Bundles einen neuen
 * Content-Hash — gemessen: 28 von 101 Chunks (1,07 MB) änderten ihren
 * Dateinamen, obwohl sich keine Zeile Quellcode geändert hatte, darunter
 * jedes Entry-Bundle der SEO-Seiten (site, story, news, search, research,
 * articles, index, main, registry).
 *
 * Die Folge stand im nginx-Log: Googlebot verbrauchte 588 von 872 Requests
 * (67 %) auf /assets/ statt auf Seiten, dazu 37 × 404 auf Hashes, die ein
 * Deploy gelöscht hatte (10.–12.09.2026). Bei 41 Deploys an einem Tag konnte
 * kein Renderer-Cache überleben.
 *
 * /assets/ ist ein Jahr `immutable` gecacht, .html trägt `no-cache`
 * (ancientnerds-nginx-config). Ein Wert, der sich pro Deploy ändert, gehört
 * deshalb ins HTML: der Cache-Buster bleibt pro Deploy frisch, die Chunks
 * bleiben über Deploys hinweg byte-identisch.
 */

function readMeta(name: string, fallback: string): string {
  // renderToString() läuft ohne document — der SSR-Pfad nutzt keinen der
  // beiden Werte, der Fallback ist dort nur Formsache.
  if (typeof document === 'undefined') return fallback
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute('content') || fallback
}

/** Kurzer Commit-Hash des Builds. Cache-Buster und Anzeige im Disclaimer. */
export const BUILD_HASH = readMeta('an-build-hash', 'dev')

/** ISO-Zeitstempel des Builds. Nur Anzeige. */
export const BUILD_TIME = readMeta('an-build-time', '')

/** `_v=<hash>`-Fragment für API-Aufrufe, die der Service Worker cacht. */
export const CACHE_BUSTER = `_v=${BUILD_HASH}`
