\pset pager off
\echo === V: thumbnail_url Formen (nicht-http) ===
SELECT left(thumbnail_url, 70) AS sample, count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND thumbnail_url IS NOT NULL AND thumbnail_url NOT ILIKE 'http%'
GROUP BY 1 ORDER BY 2 DESC LIMIT 5;

\echo === V2: thumbnail Praefix-Muster ===
SELECT substring(thumbnail_url from '^([^/]*/[^/]*/)') AS prefix, count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND thumbnail_url IS NOT NULL AND thumbnail_url NOT ILIKE 'http%'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

\echo === W: card_stats rarity_tier Verteilung ===
SELECT rarity_tier, count(*) FROM card_stats GROUP BY 1 ORDER BY 1;

\echo === W2: card_stats Luecken ===
SELECT
  count(*) FILTER (WHERE card_description IS NULL OR card_description = '') AS no_card_desc,
  count(*) FILTER (WHERE wikidata_qid IS NULL) AS no_qid,
  count(*) FILTER (WHERE best_wiki_url IS NULL) AS no_wiki,
  count(*) FILTER (WHERE civilization IS NULL) AS no_civ,
  count(*) FILTER (WHERE confidence_score IS NULL) AS no_conf,
  count(*) FILTER (WHERE confidence_score < 0.8) AS low_conf,
  count(*) FILTER (WHERE last_enriched IS NULL) AS never_enriched,
  count(*) FILTER (WHERE inception_year IS NOT NULL) AS has_inception
FROM card_stats;

\echo === W3: inception_year vs period_start Abweichung > 300 Jahre ===
SELECT count(*) FROM card_stats c JOIN unified_sites u ON u.id=c.site_id
WHERE u.source_id='ancient_nerds' AND c.inception_year IS NOT NULL AND u.period_start IS NOT NULL
  AND abs(c.inception_year - u.period_start) > 300;

\echo === X: wiki_images Groessenverteilung ===
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE is_excluded) AS excluded,
  count(*) FILTER (WHERE width IS NULL OR height IS NULL) AS no_dims,
  count(*) FILTER (WHERE least(width,height) < 500) AS small_side_lt500,
  count(*) FILTER (WHERE least(width,height) < 900) AS small_side_lt900,
  count(*) FILTER (WHERE author IS NULL OR author='') AS no_author,
  count(*) FILTER (WHERE license IS NULL OR license='') AS no_license,
  count(*) FILTER (WHERE is_hero) AS heroes
FROM wiki_images w JOIN unified_sites u ON u.id=w.site_id WHERE u.source_id='ancient_nerds';

\echo === X2: wiki_images source_type ===
SELECT source_type, count(*) FROM wiki_images GROUP BY 1 ORDER BY 2 DESC;

\echo === X3: Bilder pro Site Histogramm ===
SELECT CASE WHEN n=0 THEN '0' WHEN n<=2 THEN '1-2' WHEN n<=5 THEN '3-5' WHEN n<=10 THEN '6-10'
            WHEN n<=30 THEN '11-30' ELSE '31+' END AS bucket, count(*) FROM (
  SELECT u.id, count(w.id) AS n FROM unified_sites u
  LEFT JOIN wiki_images w ON w.site_id=u.id AND NOT coalesce(w.is_excluded,false)
  WHERE u.source_id='ancient_nerds' GROUP BY u.id
) t GROUP BY 1 ORDER BY 1;

\echo === Y: Bilder mit Titel, der einen ANDEREN Site-Namen enthaelt (Stichprobe) ===
SELECT count(*) FROM wiki_images w
JOIN unified_sites u ON u.id=w.site_id AND u.source_id='ancient_nerds'
WHERE EXISTS (
  SELECT 1 FROM unified_sites o
  WHERE o.source_id='ancient_nerds' AND o.id <> u.id AND length(o.name) > 7
    AND w.title ILIKE '%'||o.name||'%'
    AND w.title NOT ILIKE '%'||u.name||'%'
);

\echo === Z: 15 Sites ohne period_start ===
SELECT name, country, site_type FROM unified_sites
WHERE source_id='ancient_nerds' AND period_start IS NULL ORDER BY name;

\echo === Z2: nicht-kanonisches period_name ===
SELECT period_name, min(period_start), max(period_start), count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND period_name = '> 1500 AD' GROUP BY 1;

\echo === AA: site_content_links Abdeckung ancient_nerds ===
SELECT count(DISTINCT u.id) AS sites_with_links FROM unified_sites u
JOIN site_content_links l ON l.site_id=u.id WHERE u.source_id='ancient_nerds';

\echo === AB: unified_site_names fuer ancient_nerds ===
SELECT count(*) AS names, count(DISTINCT site_id) AS sites FROM unified_site_names
WHERE site_id IN (SELECT id FROM unified_sites WHERE source_id='ancient_nerds');
SELECT language_code, count(*) FROM unified_site_names
WHERE site_id IN (SELECT id FROM unified_sites WHERE source_id='ancient_nerds')
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

\echo === AC: last_audited Alter ===
SELECT date_trunc('month', last_audited) AS monat, count(*) FROM unified_sites
WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 1;
