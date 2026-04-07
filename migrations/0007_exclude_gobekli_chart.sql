-- Exclude the carbon-14 dates chart from Göbekli Tepe gallery
INSERT INTO wiki_images (site_id, filename, original_url, is_hero, is_lead, is_excluded, sort_order, source_type)
VALUES ('d953e9b3-de33-4c7d-9357-bbc5d94d2a16', 'excluded', 'https://upload.wikimedia.org/wikipedia/commons/4/4d/Earliest_carbon_14_dates_for_G%C3%B6bekli_Tepe_as_of_2013.jpg', false, false, true, 0, 'manual')
ON CONFLICT (site_id, original_url) DO UPDATE SET is_excluded = true;
