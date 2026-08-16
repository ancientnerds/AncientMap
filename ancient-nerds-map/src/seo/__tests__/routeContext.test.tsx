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
