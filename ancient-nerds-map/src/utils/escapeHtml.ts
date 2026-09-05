/**
 * Escape a string for insertion into HTML — text nodes and quoted attribute
 * values alike. The one definition: ApiDocsPage (JSON highlighter rendered via
 * dangerouslySetInnerHTML) and the build-time homepage hub lists
 * (src/landing/hubsHtml.ts) both go through here.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
