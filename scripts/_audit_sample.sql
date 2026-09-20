\pset pager off
\pset tuples_only on
\pset format unaligned
SELECT setseed(0.4242);
SELECT json_agg(row_to_json(t)) FROM (
  SELECT u.id::text AS site_id, u.name, u.country, u.site_type,
         u.period_start, u.period_name, u.lat, u.lon,
         left(coalesce(u.description,''), 700) AS description,
         u.source_url, u.thumbnail_url,
         c.rarity_tier, c.civilization, c.card_description,
         (SELECT count(*) FROM wiki_images w WHERE w.site_id=u.id AND NOT coalesce(w.is_excluded,false)) AS image_count,
         (u.raw_data ? 'description_citations') AS has_citations,
         (SELECT count(*) FROM site_content_links l WHERE l.site_id=u.id) AS link_count
  FROM unified_sites u JOIN card_stats c ON c.site_id=u.id
  WHERE u.source_id='ancient_nerds'
  ORDER BY c.rarity_tier DESC, random()
) t;
