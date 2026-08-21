/**
 * One share implementation for the whole app.
 *
 * Until 2026-08-20 this lived five times over (ArticlesPage, SiteCard,
 * ResearchPaperPage, and twice in SitePopup), each with its own idea of
 * what a cancelled share sheet means. They now all call this.
 */

export type ShareResult = 'shared' | 'copied' | 'cancelled'

export interface ShareOptions {
  /** Extra blurb for the native sheet — ignored by the clipboard path. */
  text?: string
  /** What lands on the clipboard, if the bare URL isn't enough. */
  copyText?: string
}

/**
 * Hand `url` to the OS share sheet, or put it on the clipboard when there
 * is none. The return value tells the caller whether to flash a "Copied"
 * confirmation — a native share needs none, the sheet is its own feedback.
 *
 * Dismissing the sheet returns 'cancelled' and copies nothing: the user
 * just said no, silently pushing the link into their clipboard anyway is
 * not what they asked for. Any other share failure does fall through to
 * the clipboard, and a clipboard rejection (denied permission, unfocused
 * document) propagates to the caller rather than being swallowed here.
 */
export async function shareOrCopy(
  title: string,
  url: string,
  options: ShareOptions = {},
): Promise<ShareResult> {
  if (navigator.share) {
    try {
      await navigator.share({ title, url, ...(options.text ? { text: options.text } : {}) })
      return 'shared'
    } catch (err) {
      if ((err as Error).name === 'AbortError') return 'cancelled'
    }
  }
  await navigator.clipboard.writeText(options.copyText ?? url)
  return 'copied'
}
