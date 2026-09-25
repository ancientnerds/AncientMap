/**
 * Page translation must not be able to blank a page.
 *
 * Chrome's built-in translation (Google Translate) replaces every text node
 * with <font><font>translated</font></font> and translates what React adds
 * later the same way. React still holds the original text node, which is now
 * detached. Removing it, or inserting a sibling in front of it, throws
 * NotFoundError, and React 18 unmounts the whole root: a blank page
 * (facebook/react#11538, open since 2017). Umami, 2026-09-20..24: eight
 * js_error "NotFoundError: Failed to execute 'removeChild'" rows from id-ID,
 * ar-EG, pt-BR and es sessions on /radar.html, site pages and /search.html;
 * reproduced on /radar.html by translating its text nodes the same way and
 * opening a site - the root emptied.
 *
 * Only a node that is attached nowhere (parentNode === null) is taken: removing
 * it is already done, and inserting before it appends, since the place it
 * held belongs to the translator's <font> now. A node under a different parent
 * is still a bug in our own code and still throws. What stays wrong: text
 * React updates in place keeps the translator's stale copy until the page is
 * translated again.
 */
export function tolerateDetachedNodes(proto: Node): () => void {
  const { removeChild, insertBefore } = proto

  proto.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode === null) return child
    return removeChild.call(this, child) as T
  }
  proto.insertBefore = function <T extends Node>(this: Node, node: T, child: Node | null): T {
    if (child !== null && child.parentNode === null) return this.appendChild(node)
    return insertBefore.call(this, node, child) as T
  }

  return () => {
    proto.removeChild = removeChild
    proto.insertBefore = insertBefore
  }
}
