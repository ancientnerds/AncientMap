// Page-side helpers of pipeline/studio/capture/sources.py, installed as window.__studio.
//   hideOverlays(): hide fixed/sticky layers (cookie bars, banners, sticky headers)
//   highlight(mode, needle): mode 'quote' finds the text (whitespace, quotes and
//     dashes normalised, case-insensitive, across inline elements) and wraps each
//     covered text piece in <mark class="__studio-hl">; mode 'anchor' outlines the
//     element with that id (our paper page's #ev-NN), or, when the id sits on an
//     empty span.theo-evidence-anchor (the second and later evidence ids of a
//     paragraph, plan B), the p.theo-evidence around it. Returns the highlight box
//     in page CSS pixels {x, y, w, h}, or null when nothing matches or the anchor
//     has no visible box.
//   box(): the current page box of the last highlight (after the viewport changed).
(() => {
  const NORMAL = { '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' ' }
  const normalize = (s) => {
    let out = ''
    let space = true
    for (const raw of s) {
      const c = NORMAL[raw] ?? raw
      if (/\s/.test(c)) {
        if (!space) out += ' '
        space = true
      } else {
        out += c.toLowerCase()
        space = false
      }
    }
    return out.trim()
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
      const map = []
      let space = true
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const s = node.textContent
        for (let i = 0; i < s.length; i++) {
          const c = NORMAL[s[i]] ?? s[i]
          if (/\s/.test(c)) {
            if (space) continue
            text += ' '
            space = true
          } else {
            text += c.toLowerCase()
            space = false
          }
          map.push([node, i])
        }
      }
      const q = normalize(needle)
      const at = text.indexOf(q)
      if (at < 0 || q.length === 0) return null
      const [startNode, startOffset] = map[at]
      const [endNode, endOffset] = map[at + q.length - 1]
      const range = document.createRange()
      range.setStart(startNode, startOffset)
      range.setEnd(endNode, endOffset + 1)
      const pieces = []
      const inRange = document.createTreeWalker(range.commonAncestorContainer.nodeType === 3 ? range.commonAncestorContainer.parentNode : range.commonAncestorContainer, NodeFilter.SHOW_TEXT)
      for (let node = inRange.nextNode(); node; node = inRange.nextNode()) {
        if (range.intersectsNode(node)) pieces.push(node)
      }
      const marks = []
      for (const node of pieces) {
        const s = node === startNode ? startOffset : 0
        const e = node === endNode ? endOffset + 1 : node.textContent.length
        if (e <= s) continue
        const middle = node.splitText(s)
        middle.splitText(e - s)
        const mark = document.createElement('mark')
        mark.className = '__studio-hl'
        middle.parentNode.insertBefore(mark, middle)
        mark.appendChild(middle)
        marks.push(mark)
      }
      highlighted = marks
      return unionBox(marks.flatMap((m) => [...m.getClientRects()]))
    },
    box() {
      if (highlighted.length === 0) return null
      return unionBox(highlighted.flatMap((m) => [...m.getClientRects()]))
    },
  }
})()
