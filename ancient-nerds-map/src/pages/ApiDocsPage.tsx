import { useState, useEffect, useRef } from 'react'
import PageHeader from '../components/layout/PageHeader'
import '../styles/api-docs.css'

interface OpenAPIParam {
  name: string
  in: string
  description?: string
  required?: boolean
  schema?: { type?: string; default?: unknown; minimum?: number; maximum?: number; enum?: string[] }
}

interface OpenAPIEndpoint {
  summary?: string
  description?: string
  tags?: string[]
  parameters?: OpenAPIParam[]
}

interface OpenAPISpec {
  paths: Record<string, Record<string, OpenAPIEndpoint>>
}

interface ParsedEndpoint {
  method: string
  path: string
  summary: string
  description: string
  tags: string[]
  parameters: OpenAPIParam[]
}

const TAG_ORDER = ['Sites', 'Sources', 'News', 'Stats']

/** Lightweight JSON syntax highlighter — no deps, just spans with class names. */
function highlightJson(json: string): string {
  return json.replace(
    /("(?:\\.|[^"\\])*")\s*(:)?|(\b(?:true|false|null)\b)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match, str: string | undefined, colon: string | undefined, bool: string | undefined, num: string | undefined) => {
      if (str) {
        return colon
          ? `<span class="jh-key">${str}</span>:`
          : `<span class="jh-str">${str}</span>`
      }
      if (bool) return `<span class="jh-bool">${match}</span>`
      if (num) return `<span class="jh-num">${match}</span>`
      return match
    },
  )
}

function parseSpec(spec: OpenAPISpec): ParsedEndpoint[] {
  const endpoints: ParsedEndpoint[] = []
  for (const [path, methods] of Object.entries(spec.paths)) {
    for (const [method, info] of Object.entries(methods)) {
      if (method === 'parameters') continue
      const params = (info.parameters || []).filter(
        p => p.in !== 'header' && p.name !== 'response',
      )
      endpoints.push({
        method: method.toUpperCase(),
        path,
        summary: info.summary || '',
        description: info.description || '',
        tags: info.tags || ['Other'],
        parameters: params,
      })
    }
  }
  return endpoints
}

function EndpointCard({ ep }: { ep: ParsedEndpoint }) {
  const [expanded, setExpanded] = useState(false)
  const [paramValues, setParamValues] = useState<Record<string, string>>({})
  const [response, setResponse] = useState<{ status: number; time: number; body: string } | null>(null)
  const [fetching, setFetching] = useState(false)
  const responseRef = useRef<HTMLPreElement>(null)

  const queryParams = ep.parameters.filter(p => p.in === 'query')
  const pathParams = ep.parameters.filter(p => p.in === 'path')
  const allParams = [...pathParams, ...queryParams]

  const setParam = (name: string, value: string) => {
    setParamValues(prev => ({ ...prev, [name]: value }))
  }

  const buildUrl = () => {
    let url = `/api/v1${ep.path}`
    // Substitute path params
    for (const p of pathParams) {
      const val = paramValues[p.name] || ''
      url = url.replace(`{${p.name}}`, encodeURIComponent(val))
    }
    // Add query params
    const qs = queryParams
      .map(p => {
        const val = paramValues[p.name]
        if (val === undefined || val === '') return null
        return `${encodeURIComponent(p.name)}=${encodeURIComponent(val)}`
      })
      .filter(Boolean)
    if (qs.length) url += `?${qs.join('&')}`
    return url
  }

  const execute = async () => {
    setFetching(true)
    setResponse(null)
    const url = buildUrl()
    const start = performance.now()
    try {
      const res = await fetch(url)
      const elapsed = Math.round(performance.now() - start)
      const text = await res.text()
      let body: string
      try {
        body = JSON.stringify(JSON.parse(text), null, 2)
      } catch {
        body = text
      }
      setResponse({ status: res.status, time: elapsed, body })
    } catch (err) {
      const elapsed = Math.round(performance.now() - start)
      setResponse({ status: 0, time: elapsed, body: `Network error: ${err}` })
    }
    setFetching(false)
    // Scroll response into view
    setTimeout(() => responseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
  }

  const copyResponse = () => {
    if (response) navigator.clipboard.writeText(response.body)
  }

  const copyCurl = () => {
    const url = `${window.location.origin}${buildUrl()}`
    navigator.clipboard.writeText(`curl "${url}"`)
  }

  return (
    <div className={`api-card${expanded ? ' expanded' : ''}`}>
      <div className="api-card-header" onClick={() => setExpanded(!expanded)}>
        <span className="api-method-badge">{ep.method}</span>
        <code className="api-path">{ep.path}</code>
        <span className="api-card-summary">{ep.summary}</span>
        <svg className={`api-card-chevron${expanded ? ' open' : ''}`} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>

      {expanded && (
        <div className="api-card-body">
          {ep.description && <p className="api-card-desc">{ep.description}</p>}

          {/* Parameter inputs */}
          {allParams.length > 0 && (
            <div className="api-card-params">
              <div className="api-card-params-label">Parameters</div>
              {allParams.map(p => (
                <div key={p.name} className="api-param-row">
                  <div className="api-param-row-left">
                    <code className="api-param-name">{p.name}</code>
                    {p.required && <span className="api-param-req">required</span>}
                    <span className="api-param-type">{p.schema?.type || 'string'}</span>
                  </div>
                  <input
                    className="api-param-input"
                    type="text"
                    placeholder={p.description || p.name}
                    value={paramValues[p.name] || ''}
                    onChange={e => setParam(p.name, e.target.value)}
                    onClick={e => e.stopPropagation()}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Execute bar */}
          <div className="api-exec-bar">
            <button
              className="api-exec-btn"
              onClick={execute}
              disabled={fetching}
            >
              {fetching ? 'Sending...' : 'Execute'}
            </button>
            <button className="api-exec-secondary" onClick={copyCurl}>
              Copy cURL
            </button>
            <code className="api-exec-url">{buildUrl()}</code>
          </div>

          {/* Response */}
          {response && (
            <div className="api-response">
              <div className="api-response-header">
                <span className={`api-response-status${response.status >= 200 && response.status < 300 ? ' ok' : ' err'}`}>
                  {response.status || 'ERR'}
                </span>
                <span className="api-response-time">{response.time}ms</span>
                <button className="api-response-copy" onClick={copyResponse}>Copy</button>
              </div>
              <pre
                className="api-response-body"
                ref={responseRef}
                dangerouslySetInnerHTML={{ __html: highlightJson(response.body) }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ApiDocsPage() {
  const [endpoints, setEndpoints] = useState<ParsedEndpoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const baseUrl = `${window.location.origin}/api/v1`

  useEffect(() => {
    fetch('/api/v1/openapi.json')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((spec: OpenAPISpec) => {
        setEndpoints(parseSpec(spec))
        setLoading(false)
      })
      .catch(err => {
        setError(`Failed to load API spec: ${err.message}`)
        setLoading(false)
      })
  }, [])

  const copyBaseUrl = () => {
    navigator.clipboard.writeText(baseUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Group by tag
  const byTag: Record<string, ParsedEndpoint[]> = {}
  for (const ep of endpoints) {
    const tag = ep.tags[0] || 'Other'
    ;(byTag[tag] ??= []).push(ep)
  }
  const sortedTags = TAG_ORDER.filter(t => byTag[t]).concat(
    Object.keys(byTag).filter(t => !TAG_ORDER.includes(t)),
  )

  if (loading) {
    return (
      <div className="api-page">
        <PageHeader currentPage="api" hideLyra>
          <span className="page-header-title">API Documentation</span>
        </PageHeader>
        <div className="api-status">Loading API documentation...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="api-page">
        <PageHeader currentPage="api" hideLyra>
          <span className="page-header-title">API Documentation</span>
        </PageHeader>
        <div className="api-status api-status-error">{error}</div>
      </div>
    )
  }

  return (
    <div className="api-page">
      <PageHeader currentPage="api" hideLyra>
        <span className="page-header-title">API Documentation</span>
      </PageHeader>

      <div className="api-content">
        <div className="api-info-bar">
          <div className="api-base-url" onClick={copyBaseUrl} title="Click to copy">
            <span className="api-base-label">BASE URL</span>
            <code>{baseUrl}</code>
            <span className="api-copy-hint">{copied ? 'Copied!' : 'Copy'}</span>
          </div>
          <div className="api-rate-pill">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            10 req/min
          </div>
        </div>

        <p className="api-intro-text">
          Read-only access to 750K+ archaeological sites, data sources, news, and statistics.
          All responses are JSON. Rate limit headers included in every response.
        </p>

        {sortedTags.map(tag => (
          <div key={tag} className="api-section">
            <h2 className="api-section-label">{tag}</h2>
            {byTag[tag].map(ep => (
              <EndpointCard key={`${ep.method}:${ep.path}`} ep={ep} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
