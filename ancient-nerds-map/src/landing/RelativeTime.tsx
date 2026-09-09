import { useEffect, useState } from 'react'

import { shortDate } from '../seo/display'
import { formatRelativeDate } from '../utils/formatters'

/**
 * Server and first client render show the absolute date ("Sep 7"); after
 * hydration the text becomes relative ("2h ago"). Rendering the relative
 * form on the server would differ from the client by the request/response
 * gap and trip React's hydration check.
 */
export default function RelativeTime({ iso }: { iso: string }) {
  const [text, setText] = useState(() => shortDate(iso))
  useEffect(() => {
    setText(formatRelativeDate(iso))
  }, [iso])
  return <time dateTime={iso}>{text}</time>
}
