/**
 * Rendert die indexierten Seiten serverseitig. Einziger Aufrufer: der API-Container.
 *
 * Bewusst ohne Framework — ein POST-Endpunkt und ein Healthcheck.
 */

import { createServer } from 'node:http'

import { render } from '../dist-ssr/entry-server.js'

const PORT = Number(process.env.SSR_PORT || 8500)

createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end('{"status":"ok"}')
    return
  }
  if (req.method !== 'POST' || req.url !== '/render') {
    res.writeHead(404).end()
    return
  }
  let body = ''
  req.on('data', c => (body += c))
  req.on('end', () => {
    try {
      const out = render(JSON.parse(body))
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify(out))
    } catch (err) {
      // Laut scheitern: der API-Container macht daraus ein 502.
      res.writeHead(500, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: String(err && err.message ? err.message : err) }))
    }
  })
}).listen(PORT, () => console.log(`ssr listening on ${PORT}`))
