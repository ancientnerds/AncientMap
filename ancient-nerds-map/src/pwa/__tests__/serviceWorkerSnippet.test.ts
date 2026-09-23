/**
 * Which built HTML entry gets which service-worker snippet
 * (vite.config.ts → tuneLandingHtml). The globe gets none: it registers the
 * worker as the last task of its background queue (registerServiceWorker).
 * Until that task exists, globe.html registers no worker at all.
 */

import { describe, expect, it } from 'vitest'

import { SW_INSTALL, SW_UPDATE_ONLY, serviceWorkerSnippetFor } from '../serviceWorkerSnippet'

describe('serviceWorkerSnippetFor', () => {
  it('gives the globe no snippet (it registers the worker itself, late)', () => {
    expect(serviceWorkerSnippetFor('/repo/ancient-nerds-map/globe.html')).toBeNull()
  })

  it('gives the dashboard no snippet (stats host, /sw.js is not ours there)', () => {
    expect(serviceWorkerSnippetFor('/repo/ancient-nerds-map/dashboard.html')).toBeNull()
  })

  it.each(['index.html', 'site.html', 'story.html', 'research.html', 'articles.html'])(
    'gives the SSR/landing template %s the update-only snippet',
    name => {
      expect(serviceWorkerSnippetFor(`/repo/ancient-nerds-map/${name}`)).toBe(SW_UPDATE_ONLY)
    }
  )

  it.each(['lyra.html', 'search.html', 'news.html'])('gives %s the install snippet', name => {
    expect(serviceWorkerSnippetFor(`/repo/ancient-nerds-map/${name}`)).toBe(SW_INSTALL)
  })

  it('installs the same worker as registerServiceWorker; update-only never installs one', () => {
    expect(SW_INSTALL).toContain('navigator.serviceWorker.register("/sw.js",{scope:"/"})')
    expect(SW_INSTALL).toContain('addEventListener("load"')
    expect(SW_UPDATE_ONLY).not.toContain('register(')
    expect(SW_UPDATE_ONLY).toContain('getRegistration()')
  })
})
