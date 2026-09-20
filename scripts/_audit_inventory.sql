\pset pager off
\echo === A: Feldabdeckung ancient_nerds ===
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE period_start IS NULL) AS no_period_start,
  count(*) FILTER (WHERE period_end IS NULL) AS no_period_end,
  count(*) FILTER (WHERE period_name IS NULL) AS no_period_name,
  count(*) FILTER (WHERE site_type IS NULL OR site_type ILIKE 'unknown') AS no_type,
  count(*) FILTER (WHERE country IS NULL OR country = '') AS no_country,
  count(*) FILTER (WHERE description IS NULL OR length(description) < 40) AS thin_desc,
  count(*) FILTER (WHERE source_url IS NULL OR source_url = '') AS no_source_url,
  count(*) FILTER (WHERE thumbnail_url IS NULL OR thumbnail_url = '') AS no_thumb,
  count(*) FILTER (WHERE last_audited IS NULL) AS never_audited,
  count(*) FILTER (WHERE parent_site_id IS NOT NULL) AS has_parent
FROM unified_sites WHERE source_id = 'ancient_nerds';

\echo === B: edited_by Verteilung ===
SELECT edited_by, count(*) FROM unified_sites WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 2 DESC;

\echo === C: period_start Buckets + Grenzwerte ===
SELECT period_name, count(*) AS n,
       count(*) FILTER (WHERE period_start IN (-4500,-3000,-1500,-500,1,500,1000,1500)) AS on_bucket_edge
FROM unified_sites WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 2 DESC;

\echo === D: period_name inkonsistent (grobe Heuristik) ===
SELECT count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND period_start IS NOT NULL AND period_name IS NULL;

\echo === E: period_start > 1500 auf nicht-Museum ===
SELECT count(*) FROM unified_sites
WHERE source_id='ancient_nerds' AND period_start > 1500 AND coalesce(site_type,'') NOT ILIKE '%museum%';

\echo === F: site_type Verteilung (Top 40) ===
SELECT site_type, count(*) FROM unified_sites WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 2 DESC LIMIT 40;

\echo === F2: Anzahl distinct site_type ===
SELECT count(DISTINCT site_type) FROM unified_sites WHERE source_id='ancient_nerds';

\echo === G: Laender Top 25 + NULL ===
SELECT coalesce(country,'<NULL>') AS country, count(*) FROM unified_sites WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 2 DESC LIMIT 25;

\echo === H: Koordinaten-Auffaelligkeiten ===
SELECT
  count(*) FILTER (WHERE lat = 0 AND lon = 0) AS null_island,
  count(*) FILTER (WHERE abs(lat) > 85) AS polar,
  count(*) FILTER (WHERE round(lat::numeric,4) = round(lat::numeric,0) AND round(lon::numeric,4) = round(lon::numeric,0)) AS integer_coords,
  count(*) FILTER (WHERE round(lat::numeric,2) = lat::numeric AND round(lon::numeric,2) = lon::numeric) AS two_decimals_only
FROM unified_sites WHERE source_id='ancient_nerds';

\echo === I: Duplikate innerhalb ancient_nerds nach name_normalized ===
SELECT count(*) AS dup_groups, coalesce(sum(n),0) AS dup_rows FROM (
  SELECT name_normalized, count(*) AS n FROM unified_sites
  WHERE source_id='ancient_nerds' GROUP BY 1 HAVING count(*) > 1
) t;

\echo === I2: raeumliche Near-Duplikate (<300m, aehnlicher Name) ===
SELECT count(*) FROM (
  SELECT a.id FROM unified_sites a JOIN unified_sites b
    ON a.source_id='ancient_nerds' AND b.source_id='ancient_nerds' AND a.id < b.id
   AND ST_DWithin(a.geom::geography, b.geom::geography, 300)
   AND similarity(a.name_normalized, b.name_normalized) > 0.5
) t;

\echo === J: Namens-Hygiene ===
SELECT
  count(*) FILTER (WHERE name ~ ',\s*[A-Z]') AS comma_country_suffix,
  count(*) FILTER (WHERE name <> btrim(name)) AS whitespace,
  count(*) FILTER (WHERE name ~* '^(archaeological site|site of|zone of|ruins of)') AS prefixed,
  count(*) FILTER (WHERE name ~ '[Ãâ�]') AS mojibake,
  count(*) FILTER (WHERE name ~ '^\d') AS starts_digit,
  count(*) FILTER (WHERE length(name) > 90) AS very_long
FROM unified_sites WHERE source_id='ancient_nerds';

\echo === K: source_url Formen ===
SELECT
  count(*) FILTER (WHERE source_url ILIKE '%wikipedia.org%') AS wikipedia,
  count(*) FILTER (WHERE source_url LIKE '%#%') AS fragment,
  count(*) FILTER (WHERE source_url NOT ILIKE 'http%') AS not_http,
  count(*) FILTER (WHERE source_url ~ ' ') AS contains_space,
  count(*) FILTER (WHERE source_url ILIKE '%wordpress%' OR source_url ILIKE '%blogspot%') AS blog
FROM unified_sites WHERE source_id='ancient_nerds';

\echo === L: thumbnail_url Hosts ===
SELECT substring(thumbnail_url from '^https?://([^/]+)') AS host, count(*)
FROM unified_sites WHERE source_id='ancient_nerds' AND thumbnail_url IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 15;

\echo === M: wiki_images Bestand ===
SELECT count(*) AS images, count(DISTINCT site_id) AS sites_with_images
FROM wiki_images WHERE site_id IN (SELECT id FROM unified_sites WHERE source_id='ancient_nerds');

\echo === M2: wiki_images Spalten ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='wiki_images' ORDER BY ordinal_position;

\echo === N: Sites ohne jedes Bild ===
SELECT count(*) FROM unified_sites u
WHERE u.source_id='ancient_nerds'
  AND NOT EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id)
  AND (u.thumbnail_url IS NULL OR u.thumbnail_url = '');

\echo === O: card_stats Spalten ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='card_stats' ORDER BY ordinal_position;

\echo === O2: card_stats Bestand ===
SELECT count(*) AS rows FROM card_stats;

\echo === P: unified_site_names ===
SELECT count(*) AS names, count(DISTINCT site_id) AS sites FROM unified_site_names;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='unified_site_names' ORDER BY ordinal_position;

\echo === Q: site_content_links ===
SELECT count(*) AS links, count(DISTINCT site_id) AS sites FROM site_content_links;

\echo === R: site_external_ids ===
SELECT count(*) AS ids, count(DISTINCT site_id) AS sites FROM site_external_ids;

\echo === S: raw_data Keys (Top 30) ===
SELECT k, count(*) FROM unified_sites, jsonb_object_keys(raw_data) k
WHERE source_id='ancient_nerds' GROUP BY 1 ORDER BY 2 DESC LIMIT 30;

\echo === T: Beschreibungen mit Zitaten ===
SELECT
  count(*) FILTER (WHERE raw_data ? 'description_citations') AS with_citations,
  count(*) FILTER (WHERE raw_data ? 'description_pre_enrichment') AS with_backup,
  count(*) FILTER (WHERE description ~ '\[\d+\]') AS markers_in_text
FROM unified_sites WHERE source_id='ancient_nerds';

\echo === U: parent_site_id Integritaet ===
SELECT
  count(*) FILTER (WHERE parent_site_id = id) AS self_ref,
  count(*) FILTER (WHERE parent_site_id IS NOT NULL AND parent_site_id NOT IN (SELECT id FROM unified_sites)) AS dangling
FROM unified_sites WHERE source_id='ancient_nerds';
