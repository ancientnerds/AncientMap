/**
 * @vitest-environment jsdom
 *
 * Page translation (Chrome's built-in Google Translate) swaps every text node
 * for <font><font>translated</font></font>. React still holds the original,
 * now detached, text node; removing it threw NotFoundError and React 18
 * unmounted the whole root. Umami, 2026-09-20..24: eight such js_error rows
 * from id-ID, ar-EG, pt-BR and es sessions on /radar.html, site pages and
 * /search.html. The crash on /radar.html came from SitePopup's
 * `Searching {n} sources...` - three text nodes in one span.
 */

import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { tolerateDetachedNodes } from '../translatedDom'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/** What the translator does to a rendered subtree: every text node replaced. */
function translate(root: Element): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    const outer = document.createElement('font')
    const inner = document.createElement('font')
    inner.textContent = `[${node.nodeValue}]`
    outer.appendChild(inner)
    node.parentNode!.replaceChild(outer, node)
  }
}

/** The other shape: every text node kept, but moved into a wrapper of the
 *  translator's (an extension or Edge's translator) - still inside the parent
 *  React knows, one level deeper. */
function wrap(root: Element): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    const wrapper = document.createElement('font')
    node.parentNode!.insertBefore(wrapper, node)
    wrapper.appendChild(node)
  }
}

let setDone: (done: boolean) => void = () => {}

/** SitePopup's connector summary: one span, its text split by JSX. */
function Summary({ sources }: { sources: number }) {
  const [done, set] = useState(false)
  setDone = set
  return (
    <div>
      <span className="summary">
        {done ? `Found in ${sources} sources` : <>Searching {sources} sources...</>}
      </span>
    </div>
  )
}

/** A text sibling that React later inserts an element in front of. */
function Label() {
  const [done, set] = useState(false)
  setDone = set
  return <b>{done && <i>new</i>}Label</b>
}

const roots: Root[] = []
let uninstall: (() => void) | null = null

async function mount(node: React.ReactNode): Promise<HTMLDivElement> {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  roots.push(root)
  await act(async () => root.render(node))
  return container
}

afterEach(async () => {
  uninstall?.()
  uninstall = null
  for (const root of roots.splice(0)) await act(async () => root.unmount())
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('tolerateDetachedNodes', () => {
  it('reproduces the crash: without it a translated page empties its root', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    // React reports the crash as an uncaught window error too; keep jsdom quiet.
    const quiet = (e: ErrorEvent) => e.preventDefault()
    window.addEventListener('error', quiet)
    const container = await mount(<Summary sources={2} />)
    translate(container)
    let thrown: unknown = null
    try {
      await act(async () => setDone(true))
    } catch (e) {
      thrown = e
    }
    window.removeEventListener('error', quiet)
    expect(String(thrown)).toContain('NotFoundError')
    expect(container.childElementCount).toBe(0)
  })

  it('keeps a translated page alive when React removes a text node the translator replaced', async () => {
    uninstall = tolerateDetachedNodes(Node.prototype)
    const container = await mount(<Summary sources={2} />)
    translate(container)
    await act(async () => setDone(true))
    expect(container.querySelector('.summary')!.textContent).toContain('Found in 2 sources')
  })

  it('keeps a translated page alive when React inserts before a text node the translator replaced', async () => {
    uninstall = tolerateDetachedNodes(Node.prototype)
    const container = await mount(<Label />)
    translate(container)
    await act(async () => setDone(true))
    expect(container.querySelector('b i')!.textContent).toBe('new')
  })

  it('reproduces the second crash: a wrapped text node empties the root too', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const quiet = (e: ErrorEvent) => e.preventDefault()
    window.addEventListener('error', quiet)
    const container = await mount(<Summary sources={2} />)
    wrap(container)
    let thrown: unknown = null
    try {
      await act(async () => setDone(true))
    } catch (e) {
      thrown = e
    }
    window.removeEventListener('error', quiet)
    expect(String(thrown)).toContain('NotFoundError')
    expect(container.childElementCount).toBe(0)
  })

  it('keeps a page alive when React removes a text node a translator wrapped', async () => {
    uninstall = tolerateDetachedNodes(Node.prototype)
    const container = await mount(<Summary sources={2} />)
    wrap(container)
    await act(async () => setDone(true))
    expect(container.querySelector('.summary')!.textContent).toBe('Found in 2 sources')
  })

  it('keeps a page alive when React inserts before a text node a translator wrapped', async () => {
    uninstall = tolerateDetachedNodes(Node.prototype)
    const container = await mount(<Label />)
    wrap(container)
    await act(async () => setDone(true))
    expect(container.querySelector('b')!.textContent).toBe('newLabel')
    expect(container.querySelector('b')!.firstChild!.nodeName).toBe('I')
  })

  it('still throws for a node that sits under a different parent: that is our bug, not the translator', () => {
    uninstall = tolerateDetachedNodes(Node.prototype)
    const a = document.createElement('div')
    const b = document.createElement('div')
    const child = b.appendChild(document.createElement('span'))
    expect(() => a.removeChild(child)).toThrow(/not a child/)
    expect(() => a.insertBefore(document.createElement('p'), child)).toThrow()
  })

  it('uninstalls back to the original methods', () => {
    const { removeChild, insertBefore } = Node.prototype
    tolerateDetachedNodes(Node.prototype)()
    expect(Node.prototype.removeChild).toBe(removeChild)
    expect(Node.prototype.insertBefore).toBe(insertBefore)
  })
})
