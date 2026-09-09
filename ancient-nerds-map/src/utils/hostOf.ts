/** Host of a URL without a leading www., '' when the URL does not parse. */
export function hostOf(url: string): string {
  // new URL wirft, wo Pythons urlparse ein leeres netloc liefert ("http://") —
  // derselbe Rückgabewert, nur als catch formuliert.
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return ''
  }
}
