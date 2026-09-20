\pset pager off
\pset tuples_only on
\pset format unaligned
SELECT setseed(0.777);
SELECT json_agg(row_to_json(t)) FROM (
  SELECT u.id::text AS site_id, u.name, u.country, u.site_type, c.rarity_tier,
         (SELECT json_agg(json_build_object(
            'title', w.title, 'filename', w.filename, 'width', w.width, 'height', w.height,
            'is_hero', w.is_hero, 'is_lead', w.is_lead, 'author', w.author,
            'commons_page_url', w.commons_page_url))
          FROM (SELECT * FROM wiki_images w2 WHERE w2.site_id=u.id
                AND NOT coalesce(w2.is_excluded,false)
                ORDER BY w2.sort_order NULLS LAST, w2.id LIMIT 20) w) AS images
  FROM unified_sites u JOIN card_stats c ON c.site_id=u.id
  WHERE u.source_id='ancient_nerds'
    AND (SELECT count(*) FROM wiki_images w3 WHERE w3.site_id=u.id AND NOT coalesce(w3.is_excluded,false)) >= 3
  ORDER BY c.rarity_tier DESC, random()
  LIMIT 40
) t;
