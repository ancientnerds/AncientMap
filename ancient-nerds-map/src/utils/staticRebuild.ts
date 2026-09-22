// POST /api/sites/rebuild-static starts a background job and answers 202 at once: the
// export takes about four minutes and nginx cuts /api/ requests at 120 s, so the old
// synchronous call never returned. GET /api/sites/rebuild-static/status reports the job
// (running | ok | error | interrupted | never_run); a 409 means one is already running,
// on this or the other API instance.

export type RebuildState = 'running' | 'ok' | 'error' | 'interrupted' | 'never_run'

type Fetch = typeof fetch
type Sleep = (ms: number) => Promise<void>

const POLL_MS = 10_000
const MAX_POLLS = 90 // 15 minutes; the export took ~4

const realSleep: Sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** 'started', or 'busy' when a rebuild is already running. Anything else throws. */
export async function startStaticRebuild(
  baseUrl: string,
  token: string,
  fetchImpl: Fetch = fetch,
): Promise<'started' | 'busy'> {
  const res = await fetchImpl(`${baseUrl}/sites/rebuild-static`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  })
  if (res.status === 409) return 'busy'
  if (!res.ok) throw new Error(`rebuild-static: HTTP ${res.status}`)
  return 'started'
}

/** Poll until the job stops running; returns its final state. Throws on a stuck job. */
export async function waitForStaticRebuild(
  baseUrl: string,
  token: string,
  fetchImpl: Fetch = fetch,
  sleep: Sleep = realSleep,
): Promise<RebuildState> {
  for (let poll = 0; poll < MAX_POLLS; poll++) {
    await sleep(POLL_MS)
    const res = await fetchImpl(`${baseUrl}/sites/rebuild-static/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`rebuild-static/status: HTTP ${res.status}`)
    const status = (await res.json()) as { state: RebuildState }
    if (status.state !== 'running') return status.state
  }
  throw new Error('rebuild-static still running after 15 minutes')
}

/**
 * Rebuild the static data so it includes everything committed so far. When a rebuild is
 * already running it may have read the sites before this caller's changes, so wait for it
 * and start one more.
 */
export async function rebuildStaticData(
  baseUrl: string,
  token: string,
  fetchImpl: Fetch = fetch,
  sleep: Sleep = realSleep,
): Promise<RebuildState> {
  if ((await startStaticRebuild(baseUrl, token, fetchImpl)) === 'busy') {
    await waitForStaticRebuild(baseUrl, token, fetchImpl, sleep)
    await startStaticRebuild(baseUrl, token, fetchImpl)
  }
  return waitForStaticRebuild(baseUrl, token, fetchImpl, sleep)
}
