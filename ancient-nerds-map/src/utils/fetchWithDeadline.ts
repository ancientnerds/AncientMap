/**
 * A GET for JSON that the globe's start must never wait on for long (the IP
 * lookup, the focus site's position). Module scope touches no browser global
 * (SSR-safe import).
 */

/**
 * GET JSON with a deadline that also covers the body. Rejects with
 * `<url>: no answer within <ms> ms` when the deadline passes, with
 * `<url>: HTTP <status>` on an error status, and with the outer signal's
 * reason when the caller aborts.
 */
export async function fetchJsonWithDeadline(url: string, outer: AbortSignal, ms: number): Promise<unknown> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(new Error(`${url}: no answer within ${ms} ms`)), ms)
  const onOuter = () => ctrl.abort(outer.reason)
  outer.addEventListener('abort', onOuter)
  try {
    const res = await fetch(url, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    // fetch rejects with its own AbortError; name the deadline or the caller's reason instead
    if (ctrl.signal.aborted) throw ctrl.signal.reason
    throw err
  } finally {
    clearTimeout(timer)
    outer.removeEventListener('abort', onOuter)
  }
}
