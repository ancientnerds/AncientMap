import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { RouteProvider, useRoute } from '../RouteContext'

function Probe() {
  const route = useRoute()
  return <span>{route?.type ?? 'none'}</span>
}

describe('RouteProvider', () => {
  it('liefert das Payload serverseitig, ohne window zu berühren', () => {
    const html = renderToString(
      <RouteProvider value={{ type: 'sitesIndex', countries: [] }}>
        <Probe />
      </RouteProvider>,
    )
    expect(html).toContain('sitesIndex')
  })

  it('liefert undefined ohne Provider statt zu werfen', () => {
    const html = renderToString(<Probe />)
    expect(html).toContain('none')
  })
})

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}

describe('kein direkter window.__AN_ROUTE__-Zugriff mehr', () => {
  it('nur RouteContext.tsx darf __AN_ROUTE__ lesen', () => {
    // __tests__ ist ausgenommen: diese Datei nennt das Token selbst.
    const offenders = walk('src')
      .filter(f => /\.tsx?$/.test(f) && !f.includes('RouteContext') && !f.includes('__tests__'))
      .filter(f => readFileSync(f, 'utf8').includes('__AN_ROUTE__'))
    expect(offenders).toEqual([])
  })
})
