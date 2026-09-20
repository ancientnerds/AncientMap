\pset pager off
\echo === AD: Mojibake-Namen ===
SELECT name, country FROM unified_sites WHERE source_id='ancient_nerds' AND name ~ '[Ãâ]' LIMIT 20;

\echo === AE: period_start > 1500, nicht Museum ===
SELECT name, country, site_type, period_start FROM unified_sites
WHERE source_id='ancient_nerds' AND period_start > 1500 AND coalesce(site_type,'') NOT ILIKE '%museum%'
ORDER BY period_start DESC LIMIT 40;

\echo === AF: Namen mit ", X"-Anhang (Stichprobe) ===
SELECT name, country FROM unified_sites WHERE source_id='ancient_nerds' AND name ~ ',\s*[A-Z]' ORDER BY random() LIMIT 20;

\echo === AG: Praefix-Namen ===
SELECT name FROM unified_sites WHERE source_id='ancient_nerds' AND name ~* '^(archaeological site|site of|zone of|ruins of)' LIMIT 30;

\echo === AH: raeumliche Near-Duplikate im Detail ===
SELECT a.name AS name_a, b.name AS name_b, a.country,
       round(ST_Distance(a.geom::geography, b.geom::geography)::numeric) AS meter
FROM unified_sites a JOIN unified_sites b
  ON a.source_id='ancient_nerds' AND b.source_id='ancient_nerds' AND a.id < b.id
 AND ST_DWithin(a.geom::geography, b.geom::geography, 300)
 AND similarity(a.name_normalized, b.name_normalized) > 0.5
ORDER BY meter LIMIT 30;

\echo === AI: nicht-http source_url ===
SELECT name, source_url FROM unified_sites
WHERE source_id='ancient_nerds' AND source_url IS NOT NULL AND source_url NOT ILIKE 'http%';

\echo === AJ: Geological interest + suspect_modern ===
SELECT site_type, count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND site_type IN ('Geological interest','suspect_modern','Archaeological site','Site','Unknown','Ruin','Natural feature','Museum')
GROUP BY 1 ORDER BY 2 DESC;

\echo === AK: site_type Werte ausserhalb der haeufigen (Rest) ===
SELECT site_type, count(*) FROM unified_sites WHERE source_id='ancient_nerds'
GROUP BY 1 HAVING count(*) <= 10 ORDER BY 2 DESC;

\echo === AL: Tabellen mit site-Bezug ===
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;

\echo === AM: card_stats civilization = Laendername? ===
SELECT count(*) FROM card_stats c JOIN unified_sites u ON u.id=c.site_id
WHERE u.source_id='ancient_nerds' AND c.civilization = u.country;

\echo === AM2: civilization Top 25 ===
SELECT civilization, count(*) FROM card_stats GROUP BY 1 ORDER BY 2 DESC LIMIT 25;

\echo === AN: site_external_ids Typen ===
SELECT id_type, count(*) FROM site_external_ids GROUP BY 1 ORDER BY 2 DESC;

\echo === AO: site_content_links Qualitaet ===
SELECT link_type, count(*) FROM site_content_links GROUP BY 1 ORDER BY 2 DESC LIMIT 15;

\echo === AP: Beschreibungslaengen ===
SELECT width_bucket(length(description), 0, 2000, 10) AS bucket,
       min(length(description)) AS min_len, max(length(description)) AS max_len, count(*)
FROM unified_sites WHERE source_id='ancient_nerds' AND description IS NOT NULL
GROUP BY 1 ORDER BY 1;
