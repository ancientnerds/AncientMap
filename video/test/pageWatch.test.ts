/**
 * onNvidia's page watch (scripts/cli.ts watchPages, owner decision Q17): a
 * page of the proved browser that is closed from outside or crashes cancels
 * the render at once, instead of leaving a frame to Remotion's ready timeout.
 * No GPU and no Chrome: FakeCdp stands in for Remotion's CDP connection
 * (HeadlessBrowser.connection) and delivers the events the way Remotion
 * 4.0.529's browser/Connection.js does. A top-level Target.attachedToTarget or
 * Target.detachedFromTarget is emitted on the connection, after the session
 * is created or closed; a page's Inspector.targetCrashed is emitted on its
 * session. test/gpu/crash.gpu.ts proves the same with a real render tab on
 * the RTX 3080.
 */
import { EventEmitter } from 'node:events'

import { describe, expect, it } from 'vitest'

import { PAGE_CLOSED, PAGE_CRASHED, watchPages } from '../scripts/cli'

type Connection = Parameters<typeof watchPages>[0]
type Listener = Parameters<EventEmitter['on']>[1]

class FakeCdp {
  readonly events = new EventEmitter()
  readonly sessions = new Map<string, EventEmitter>()
  readonly sent: [string, unknown][] = []

  on(event: string, handler: Listener): this {
    this.events.on(event, handler)
    return this
  }

  off(event: string, handler: Listener): this {
    this.events.off(event, handler)
    return this
  }

  session(sessionId: string): EventEmitter | null {
    return this.sessions.get(sessionId) ?? null
  }

  send(method: string, params?: unknown): Promise<{ value: object; size: number }> {
    this.sent.push([method, params])
    return Promise.resolve({ value: {}, size: 0 })
  }

  /** Chrome attached a session to a target: Connection.js creates the session, then emits the event. */
  attach(sessionId: string, targetId: string, type: string): void {
    this.sessions.set(sessionId, new EventEmitter())
    this.events.emit('Target.attachedToTarget', { sessionId, targetInfo: { targetId, type }, waitingForDebugger: false })
  }

  /** The target went: Connection.js closes the session, then emits the event. */
  detach(sessionId: string, targetId: string): void {
    this.sessions.delete(sessionId)
    this.events.emit('Target.detachedFromTarget', { sessionId, targetId })
  }

  crash(sessionId: string): void {
    const session = this.sessions.get(sessionId)
    if (!session) throw new Error(`no session ${sessionId}`)
    session.emit('Inspector.targetCrashed', {})
  }

  get connection(): Connection {
    return this as unknown as Connection
  }
}

function watched() {
  const cdp = new FakeCdp()
  const losses: string[] = []
  const stop = watchPages(cdp.connection, (why) => losses.push(why))
  return { cdp, losses, stop }
}

describe('onNvidia cancels at once when a page of the proved browser is lost (owner decision Q17)', () => {
  it('a page closed from outside is reported the moment its session detaches', () => {
    const { cdp, losses } = watched()
    cdp.attach('s1', 't1', 'page')
    expect(losses).toEqual([])
    cdp.detach('s1', 't1')
    expect(losses).toEqual([PAGE_CLOSED])
  })

  it('a crashed page is reported the moment Chrome says so', () => {
    const { cdp, losses } = watched()
    cdp.attach('s1', 't1', 'page')
    cdp.crash('s1')
    expect(losses).toEqual([PAGE_CRASHED])
  })

  it('a page Remotion closes itself (Target.closeTarget over the connection) is no loss, and the command still goes out', async () => {
    const { cdp, losses } = watched()
    cdp.attach('s1', 't1', 'page')
    cdp.attach('s2', 't2', 'page')
    await cdp.connection.send('Target.closeTarget', { targetId: 't1' })
    expect(cdp.sent).toEqual([['Target.closeTarget', { targetId: 't1' }]])
    cdp.detach('s1', 't1')
    expect(losses).toEqual([])
    // Only the page Remotion closed is exempt.
    cdp.detach('s2', 't2')
    expect(losses).toEqual([PAGE_CLOSED])
  })

  it('other commands pass through untouched', async () => {
    const { cdp, losses } = watched()
    cdp.attach('s1', 't1', 'page')
    await cdp.connection.send('Target.attachToTarget', { targetId: 't1', flatten: true })
    expect(cdp.sent).toEqual([['Target.attachToTarget', { targetId: 't1', flatten: true }]])
    cdp.detach('s1', 't1')
    expect(losses).toEqual([PAGE_CLOSED])
  })

  it('targets that are not pages, and sessions attached before the watch, are not watched', () => {
    const cdp = new FakeCdp()
    cdp.attach('s0', 't0', 'page')
    const losses: string[] = []
    watchPages(cdp.connection, (why) => losses.push(why))
    cdp.attach('s1', 't1', 'service_worker')
    cdp.crash('s1')
    cdp.detach('s1', 't1')
    cdp.detach('s0', 't0')
    expect(losses).toEqual([])
  })

  it('stop() ends the watch and gives the connection its own send back', () => {
    const { cdp, losses, stop } = watched()
    cdp.attach('s1', 't1', 'page')
    cdp.attach('s2', 't2', 'page')
    expect(cdp.send).not.toBe(FakeCdp.prototype.send)
    stop()
    expect(cdp.send).toBe(FakeCdp.prototype.send)
    cdp.crash('s1')
    cdp.detach('s2', 't2')
    cdp.attach('s3', 't3', 'page')
    cdp.detach('s3', 't3')
    expect(losses).toEqual([])
    expect(cdp.events.listenerCount('Target.attachedToTarget')).toBe(0)
    expect(cdp.events.listenerCount('Target.detachedFromTarget')).toBe(0)
    expect(cdp.sessions.get('s1')?.listenerCount('Inspector.targetCrashed')).toBe(0)
  })
})
