# Story text with foreign script, corrected 2026-10-01

Six `news_items` rows carried text in a script the site does not write (found by the Theo language-bleed
detector, `pipeline/lyra/theo_citations.py`, run over all 3,489 stories). Owner approval 2026-10-01
("Ja, alle 6 wie vorgelegt") after the per-row diff in `DIFF.txt` had been shown.

| Story | Change | Cause |
|---|---|---|
| 8351 | `Локалитет Беловоде код Петровца на Млави` -> `Belovode` (headline, summary, post, 2 facts) | boot migration v14 wrote the linked `osm_historic` site's name into the text |
| 8359 | `大汶口遗址公园` -> `Dawenkou` (headline, summary, post) | same, `osm_historic` |
| 6342 | `vs人工 structure` -> `vs man-made structure` | model drift into Chinese |
| 5733 | `Researchers科尔 Chromemer` -> `Researchers Cole Chromemer` (fact 6; transcript: "As Cole Chromemer") | model drift |
| 5797 | `have存在的问题` -> `have problems` (post; story withdrawn, significance 1) | model drift |
| 6266 | whole story rewritten in English from the transcript of QFPQ7jtLgB0, 17:10-20:35 | model wrote it in Chinese |

## How it was written

1. `before.json`: the six rows as production held them (read-only `json_agg` export).
2. `make_plan.py` -> `after.json`, `DIFF.txt`, `APPLY.sql`, `ROLLBACK.sql`, `CHECK_BEFORE.sql`,
   `CHECK_AFTER.sql`. Every replacement must hit; every result passes `story_script_bleed`.
   Files are written as bytes: on Windows `write_text` turned the `\n` inside story text into `\r\n`, and
   the guard for 6342 (post with line breaks) matched 0 rows until that was fixed; the guard did its job.
3. `CHECK_BEFORE.sql` (SELECT only): 6 x 1. `CHECK_AFTER.sql`: 6 x 0.
4. `APPLY.sql`: one transaction; each UPDATE guarded by all four previous values, a DO block raises unless
   exactly one row changes. Output `BEGIN / DO / COMMIT`.
5. After commit: `CHECK_AFTER.sql` 6 x 1, `CHECK_BEFORE.sql` 6 x 0; detector over all 3,489 stories: 0
   flagged; new URLs answer 200 with the new titles, the old Cyrillic URL of 8351 answers 301 to the new one.

## Watch

Boot migration v14 would have written the native-script names back into 8351 and 8359 on the next Lyra
start (they were the only two rows it would still have changed). It is gated since commit `21b8574`. A Lyra
start on older code re-breaks them; after the deploy, run `CHECK_AFTER.sql` again (expect 6 x 1).

Rollback: `ROLLBACK.sql` restores `before.json`, guarded by the `after` values.
