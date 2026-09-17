/**
 * Which question produced a given Lyra answer — the nearest user message
 * before it. The thumbs under the answer report only its LENGTH, never the
 * text (privacy.html §2a); an older answer in a long chat must not be
 * described by the newest question, which is why this walks backwards
 * instead of reading the "last question" ref.
 */
export function questionBefore(
  messages: ReadonlyArray<{ role: string; content: string }>,
  index: number
): string {
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === 'user') return messages[i].content
  }
  return ''
}
