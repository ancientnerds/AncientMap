# Webshare-Traffic-Fix für Lyra: Data-API-Prefilter vor dem Transcript-Fetch

**Kontext-Übergabe aus dem Vekthor-Projekt (2026-08-01).** Vekthor und Ancient
Nerds teilen sich denselben Webshare-Residential-Proxy-Account (`jydaujco`,
3-GB-Plan). In Vekthor wurde heute ein massives Traffic-Leck gefixt
(~92-94 % Ersparnis). Bei der Analyse sind drei Lyra-Befunde aufgefallen, die
dieses Dokument beschreibt. Ziel: dieselben Optimierungen in Lyra, damit kein
Webshare-Traffic für Videos verschwendet wird, die sowieso aussortiert werden.

Wichtig vorab: Lyra hat die Failure-Persistenz **bereits** (NewsVideo-Rows mit
status `transcribed`/`failed`/`skipped`, gedrosselte Retries, Aufgeben nach
24 h — `transcript_fetcher.py`, `retry_failed_videos()`). Das war sogar das
Vorbild für den Vekthor-Fix. Die Lücken liegen woanders: in der
**Reihenfolge** der Fetches.

## Hintergrund: Warum Transcript-Fetches teuer sind

`youtube-transcript-api` lädt bei jedem Fetch die komplette YouTube-Watch-Page
über den Proxy — **~0,3 MB gzip pro Versuch** (gemessen 2026-08-01:
287-315 KB). Das eigentliche Transcript ist winzig. Jeder vermeidbare
`fetch_transcript()`-Aufruf spart also ~0,3 MB Residential-Traffic.

## Befund 1 (Hauptfix): Duration-/Members-Check erst NACH dem Proxy-Fetch

In `pipeline/lyra/transcript_fetcher.py`, `fetch_new_videos()`:

1. `fetch_transcript(video_info["id"], settings)` läuft zuerst (~Zeile 268)
   — **Watch-Page über Webshare schon gezogen**.
2. Der `min_video_minutes`-Check kommt danach (~Zeile 290), weil die Dauer
   aus dem Transcript selbst berechnet wird (letztes Segment).
3. `_fetch_metadata_youtube_api()` (videos.list) läuft ebenfalls erst danach
   (~Zeile 308).

Folge: Jedes zu kurze Video (Shorts!), jedes members-only/private Video
kostet erst eine Watch-Page über den Proxy, bevor es aussortiert wird.
`SKIP_TITLE_KEYWORDS` (trailer/teaser/promo) fängt nur einen Teil ab.

**Fix — Reihenfolge drehen (Referenz: Vekthor-Implementierung, s.u.):**

- Nach `get_recent_videos()` (playlistItems, liefert KEINE Dauer) einen
  **Batch-Call `videos.list` mit `part=snippet,contentDetails`** für alle
  neuen IDs machen (1 Quota-Unit pro 50 IDs, ohne Proxy, direkt).
- **ID fehlt in der Antwort** → privat/members-only/gelöscht → sofort
  NewsVideo-Row mit `status="skipped"` anlegen, **nie** `fetch_transcript()`
  aufrufen.
- **`contentDetails.duration` < `min_video_minutes`** → deckt alle Shorts
  (≤ 3 min) ab → sofort `skipped`, kein Proxy-Kontakt.
- **Achtung Randfall:** Livestreams/Premieren melden `P0D`/`PT0S` bzw. keine
  Dauer. Dauer 0/unparsebar darf NICHT als „zu kurz" gewertet werden —
  sonst werden echte Videos permanent geskippt. Nur `0 < dauer < min`
  skippt.
- **Quota-/API-Fehler** beim Batch-Call → Fallback aufs bisherige Verhalten
  (Prefilter überspringen, Pipeline läuft weiter).
- Bonus: `snippet` aus demselben Call liefert description/tags — der
  bisherige `_fetch_metadata_youtube_api()`-Call pro Video (~Zeile 308) wird
  damit redundant und kann für diese IDs entfallen (spart weitere Units).

## Befund 2: Premieren-Schleife

`PremiereNotReadyError` → bewusst keine DB-Row (~Zeile 269-273) → das Video
wird **jeden Cycle erneut** über den Proxy versucht, bis die Premiere lief.
Jeder Versuch = eine Watch-Page.

**Fix:** Der `videos.list`-Batch aus Befund 1 liefert
`snippet.liveBroadcastContent` (`upcoming`/`live`/`none`). Bei
`upcoming`/`live` → deferren wie bisher (keine Row), aber **ohne**
`fetch_transcript()`-Aufruf. Erst wenn `none` gemeldet wird, das Transcript
holen. (VideoMetadata-Struktur ggf. um das Feld erweitern.)

## Befund 3: WebshareProxyConfig-Default-Retries

`_build_ytt_api()` (~Zeile 51-56) nutzt `WebshareProxyConfig` ohne
`retries_when_blocked` → Bibliotheks-Default **10**. Pro geblockter IP bis zu
10 Anläufe. Block-Pages sind klein, aber es summiert sich.

**Fix:** `WebshareProxyConfig(..., retries_when_blocked=3)` (o.ä.) explizit
setzen. Vorher kurz in der installierten Version den Parameternamen
verifizieren.

## Referenz-Implementierung (Vekthor, heute gebaut & deployed)

`C:\PythonProjects\KI-Newsletter`:

- `src/kinews/pipeline/sources/youtube.py` — Data-API-Prefilter in
  `YouTubeAdapter.fetch()`: Kandidaten sammeln → `fetch_video_metadata_batch`
  → fehlende IDs / zu kurze Dauer als permanent-skip yielden → erst dann
  Transcript über Proxy. Inkl. `P0D`-Guard und Quota-Fallback.
- `tests/unit/test_youtube_prefilter.py` — die 6 Testfälle (fehlende ID,
  Short, Dauer 0 nicht skippen, Enrichment, API-Fehler-Fallback, kein Key).
- `src/kinews/pipeline/stages/retry_transcripts.py` — Lyra-inspirierte
  Retry-Stage (in Lyra schon vorhanden, nur als Kontext).

**Regel wie immer: Pattern übernehmen, Code nicht 1:1 kopieren** — Lyra hat
eigene Strukturen (sync statt async, NewsVideo statt RawItem,
playlistItems-Discovery).

## Erwarteter Effekt (ehrliche Einschätzung)

Deutlich kleiner als bei Vekthor, weil Lyra Fehlschläge schon persistiert:
Ersparnis = 1 Watch-Page (~0,3 MB) pro Short/members/zu-kurzem Video
(einmalig je Video) + Premieren-Versuche pro Cycle bis zur Ausstrahlung +
weniger Blocked-Retries. Bei 38 Kanälen grob **einige hundert MB pro Monat**,
je nach Shorts-Anteil der Kanäle. Der eigentliche Wert: null verschwendete
Bytes für Videos, die nie in die Pipeline gehören.

## Größter Hebel (separates Projekt, nicht Teil dieses Fixes)

`LYRA_PROXY_URL` (config.py ~Zeile 219, `GenericProxyConfig`, Vorrang vor
Webshare) ist fertig designed, aber nirgends aktiviert — weder lokal noch auf
dem ancientnerds-VPS. Mit einem tinyproxy auf einem Pi im Tailscale-Netz
(Home-IP-Exit) ginge der Webshare-Verbrauch beider Projekte gegen null.
Vekthor bekäme denselben Mechanismus als `KINEWS_PROXY_URL`.
