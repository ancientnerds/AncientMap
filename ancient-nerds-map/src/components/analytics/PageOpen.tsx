/**
 * PageOpen - "diese Seite wurde gelesen", einmal pro Seitenaufruf.
 *
 * Wofuer: `story_open` und `paper_open` feuerten bisher nur aus den Karten
 * (NewsCard expand, PaperCard Klick). Wer ueber Google auf
 * /news-archive/<slug> oder /research/<slug> landet, liest die Seite, ohne je
 * ein Event auszuloesen — und das Panel "Top Stories"/"Top Papers" sortiert
 * diese Klicks. Gemessen am 04.10.2026 ueber 30 Tage: 165 Einstiegssitzungen
 * auf Story-Seiten gegen 9 `story_open`-Events insgesamt. Das Panel zeigte
 * darum eine Story, obwohl 165 Sitzungen ueber die Startseite dieses Typs
 * hereinkamen.
 *
 * `method: 'landing'` trennt den Lesezugriff von den Karten-Klicks
 * ('expand', 'page', 'overlay'), `context` den Seitentyp wie bei `site_open`.
 * Beides sind Felder, die die Abfrage bereits mitfuehrt — es ist keine neue
 * Semantik, nur eine zweite Art, dasselbe Ereignis auszuloesen.
 *
 * Der Effekt laeuft nach der Hydration (nicht im Render), damit die
 * serverseitige Seite unberuehrt bleibt und der Crawler nichts zaehlt.
 */
import { useEffect, useRef } from 'react'

import { type EventName, type EventProps, track } from '../../analytics'

export function PageOpen({ event, ...props }: { event: EventName } & EventProps): null {
  // useRef statt einer Abhaengigkeit: die Eigenschaften sind ein neues Objekt
  // bei jedem Render, eine useEffect-Abhaengigkeit wuerde also bei jedem
  // Rendern feuern. Der Ref schuetzt genau einmal.
  const sent = useRef(false)
  useEffect(() => {
    if (sent.current) return
    sent.current = true
    track(event, props)
  }, [])
  return null
}
