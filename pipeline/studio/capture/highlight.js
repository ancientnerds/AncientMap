// Page-side helpers of pipeline/studio/capture/sources.py, installed as window.__studio.
//   hideOverlays(): hide fixed/sticky layers (cookie bars, banners, sticky headers)
//   highlight(mode, needle): mode 'quote' finds the text among the text the page shows
//     its readers (whitespace, quotes and dashes normalised, case-insensitive, across
//     inline elements; <script>, <style>, hidden elements and the hidden overlays do not
//     count) and wraps each covered text piece in <mark class="__studio-hl">; mode
//     'anchor' outlines the element with that id (our paper page's #ev-NN), or, when the id
//     sits on an empty span.theo-evidence-anchor (the second and later evidence ids of a
//     paragraph, plan B), the p.theo-evidence around it. Returns the highlight box in page
//     CSS pixels {x, y, w, h}, or null when nothing matches, a piece of the quote has no
//     box, or a box around the highlight cuts part of it off from the reader (a truncated
//     paywall body, a "read more" clamp): sources.py then advises a QuoteCard. Before
//     measuring, the scrollers around the highlight are let out (unclip), so the document
//     itself scrolls: our paper page keeps html, body and #root at 100% with overflow
//     hidden and scrolls .theo-page instead (index.css, theo.css), and the capture window
//     is scrolled with window.scrollTo on a page as tall as its content.
//   box(): the current page box of the last highlight (after the viewport changed).
(() => {
  const NORMAL = { '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' ' }
  // One character (code point) folded for matching: ' ' for whitespace, else plain
  // quotes and dashes, lower-cased. The result can be longer than the character: 'İ'
  // (U+0130) lower-cases to 'i' plus a combining dot above, two UTF-16 units.
  const fold = (ch) => {
    const c = NORMAL[ch] ?? ch
    return /\s/.test(c) ? ' ' : c.toLowerCase()
  }
  const normalize = (s) => {
    let out = ''
    let space = true
    for (const ch of s) {
      const c = fold(ch)
      if (c === ' ') {
        if (!space) out += ' '
        space = true
      } else {
        out += c
        space = false
      }
    }
    return out.trim()
  }
  // A text node the reader sees: its element has a box and is not visibility:hidden. That
  // leaves out <script> (a JSON-LD articleBody), <style>, <noscript>, display:none subtrees
  // (a paywall's full text kept in the DOM) and the overlays hideOverlays() hid. An element
  // with display:contents has no box of its own (checkVisibility() is false for it): its
  // text is laid out in the nearest ancestor that has one.
  const readable = (text) => {
    let el = text.parentElement
    if (getComputedStyle(el).visibility !== 'visible') return false
    while (getComputedStyle(el).display === 'contents') el = el.parentElement
    return el.checkVisibility()
  }
  const overflows = (node) => node.scrollHeight > node.clientHeight
  const letOut = (node) => {
    node.style.setProperty('overflow', 'visible', 'important')
    node.style.setProperty('height', 'auto', 'important')
    node.style.setProperty('max-height', 'none', 'important')
  }
  // Lets the document scroll to the highlight. A box the reader scrolls (overflow-y auto or
  // scroll) is let out when its content overflows it. A box that clips (hidden, clip) is let
  // out only when it fitted its content in the page's own layout and overflows because a
  // scroller below it was let out: our paper page's #root around .theo-page (both 100% of
  // the viewport, border-box in index.css). A clipper that already overflowed hides that
  // part from its readers (a truncated paywall body, a "read more" clamp, a closed
  // accordion) and stays as it is; clipped() then finds the highlight cut off.
  const unclip = (el) => {
    const ancestors = []
    for (let node = el.parentElement; node; node = node.parentElement) ancestors.push(node)
    const overflowed = ancestors.map(overflows)
    ancestors.forEach((node, i) => {
      // read after the boxes below were let out: their overflow now shows here
      if (!overflows(node)) return
      const y = getComputedStyle(node).overflowY
      const scroller = y === 'auto' || y === 'scroll'
      const clipper = y === 'hidden' || y === 'clip'
      if (scroller || (clipper && !overflowed[i])) letOut(node)
    })
  }
  // True when a box around the element cuts part of it off: on an axis where an ancestor
  // clips its overflow, the element reaches past that ancestor's client box (1 px of slack:
  // clientWidth and clientHeight are whole pixels). Overflow does not apply to inline and
  // display:contents elements, so they clip nothing.
  const clipped = (el) => {
    const rects = [...el.getClientRects()]
    for (let node = el.parentElement; node; node = node.parentElement) {
      const style = getComputedStyle(node)
      if (style.display === 'inline' || style.display === 'contents') continue
      const clipX = style.overflowX !== 'visible'
      const clipY = style.overflowY !== 'visible'
      if (!clipX && !clipY) continue
      const outer = node.getBoundingClientRect()
      const left = outer.left + node.clientLeft
      const top = outer.top + node.clientTop
      for (const r of rects) {
        if (clipX && (r.left < left - 1 || r.right > left + node.clientWidth + 1)) return true
        if (clipY && (r.top < top - 1 || r.bottom > top + node.clientHeight + 1)) return true
      }
    }
    return false
  }
  const unionBox = (rects) => {
    const xs = rects.flatMap((r) => [r.left, r.right])
    const ys = rects.flatMap((r) => [r.top, r.bottom])
    const x = Math.min(...xs)
    const y = Math.min(...ys)
    return { x: x + scrollX, y: y + scrollY, w: Math.max(...xs) - x, h: Math.max(...ys) - y }
  }
  let highlighted = []
  window.__studio = {
    hideOverlays() {
      for (const el of document.querySelectorAll('body *')) {
        const pos = getComputedStyle(el).position
        if (pos === 'fixed' || pos === 'sticky') el.style.setProperty('display', 'none', 'important')
      }
      document.documentElement.style.setProperty('overflow', 'visible', 'important')
      document.body.style.setProperty('overflow', 'visible', 'important')
    },
    highlight(mode, needle) {
      if (mode === 'anchor') {
        const hit = document.getElementById(needle)
        if (!hit) return null
        const el = hit.classList.contains('theo-evidence-anchor') ? hit.closest('p.theo-evidence') : hit
        if (!el) return null
        unclip(el)
        if (clipped(el)) return null
        const box = unionBox([el.getBoundingClientRect()])
        if (box.w < 1 || box.h < 1) return null
        el.style.setProperty('outline', '4px solid #00cc66')
        el.style.setProperty('outline-offset', '6px')
        el.style.setProperty('background', 'rgba(0, 204, 102, 0.14)')
        highlighted = [el]
        return box
      }
      const style = document.createElement('style')
      style.textContent = 'mark.__studio-hl{background:rgba(0,204,102,.28);color:inherit;box-shadow:0 0 0 2px rgba(0,204,102,.9);border-radius:2px}'
      document.head.appendChild(style)
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      let text = ''
      // one entry per UTF-16 unit of text: [text node, start, end] of the page character
      const map = []
      let space = true
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!readable(node)) continue
        const s = node.textContent
        let start = 0
        for (const ch of s) {
          const end = start + ch.length
          const c = fold(ch)
          if (c !== ' ' || !space) {
            text += c
            for (let k = 0; k < c.length; k++) map.push([node, start, end])
            space = c === ' '
          }
          start = end
        }
      }
      const q = normalize(needle)
      const at = text.indexOf(q)
      if (at < 0 || q.length === 0) return null
      const [startNode, startOffset] = map[at]
      const [endNode, , endOffset] = map[at + q.length - 1]
      const range = document.createRange()
      range.setStart(startNode, startOffset)
      range.setEnd(endNode, endOffset)
      // the covered text nodes the search read (a hidden node inside the range is not quoted)
      const pieces = []
      const inRange = document.createTreeWalker(range.commonAncestorContainer.nodeType === 3 ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer, NodeFilter.SHOW_TEXT)
      for (let node = inRange.nextNode(); node; node = inRange.nextNode()) {
        if (range.intersectsNode(node) && readable(node)) pieces.push(node)
      }
      const marks = []
      for (const node of pieces) {
        const s = node === startNode ? startOffset : 0
        const e = node === endNode ? endOffset : node.textContent.length
        if (e <= s) continue
        const middle = node.splitText(s)
        middle.splitText(e - s)
        const mark = document.createElement('mark')
        mark.className = '__studio-hl'
        middle.parentNode.insertBefore(mark, middle)
        mark.appendChild(middle)
        marks.push(mark)
      }
      // a piece the search read can still have no box (the text of a <textarea>, of an SVG
      // <text>): that part of the quote is not on the page; collapsed white space may lack one
      if (marks.some((m) => m.textContent.trim() !== '' && m.getClientRects().length === 0)) return null
      for (const mark of marks) unclip(mark)
      if (marks.some(clipped)) return null
      highlighted = marks
      return unionBox(marks.flatMap((m) => [...m.getClientRects()]))
    },
    box() {
      if (highlighted.length === 0) return null
      return unionBox(highlighted.flatMap((m) => [...m.getClientRects()]))
    },
  }
})()
