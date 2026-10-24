-- 0031_research_paper_sites.sql
--
-- research_paper_sites: which curated sites a public Theo paper treats. The site page lists the
-- papers under "Research on this site", the paper page lists its sites (owner decision
-- 2026-10-20, SEO evaluation 2026-10-19, A2: 0 of 298 site pages linked a paper).
--
-- Why a table and not a relation derived at render time (measured read-only on production,
-- 2026-10-20, 41 public papers, 4,900 curated sites): no stored field names a site. result_json
-- carries no site id (evidence: quote/claim/source ids; probative_images: Commons metadata),
-- research_nodes.site_id is NULL on all 850 nodes of the 33 papers it covers, research_artifacts
-- exist for 5 papers only, and the 6 "/sites/" paths in the reports are foreign URLs. Matching
-- site names against the report text finds 155 (paper, site) pairs over all 41 papers with the
-- alternate names, 49 with the primary names alone - and most of them are wrong: "The Ancient
-- City of Side" in every "## The Other Side" heading, "Montana" for Malmstrom AFB, "Petra" for
-- an author named Petra Rettberg, "Alexandria in the Caucasus" for Heron of Alexandria, "Eridu"
-- for the Eridu Genesis. A render-time rule cannot tell these apart, so the relation is stored.
--
-- The seed below is the reviewed result of that match plus a second pass over the sites' unique
-- name tokens: every pair was read in its paper (claude-opus-5-5, 2026-10-20) and kept only where
-- the paper says something about that place or shows a picture of it - not a passing list item,
-- not a namesake, not a source title alone. 58 pairs, 15 papers, 47 sites. Left out because the
-- site is retired (no page): the Bosnian pyramids of the Sun and of the Moon, Yonaguni Monument.
--
-- Both keys cascade: a row means nothing once its paper or its site is gone, like the other
-- site-owned link tables (site_content_links, unified_site_names). A paper's text never changes
-- here - result_json is not read or written (journalled papers change only through theo_publish).
--
-- Forward-only and idempotent: the table is created once, each pair is inserted once
-- (ON CONFLICT DO NOTHING), and the INSERT joins the live rows, so a pair whose paper or site
-- does not exist is skipped rather than failing the deploy.

CREATE TABLE IF NOT EXISTS research_paper_sites (
    request_id uuid NOT NULL REFERENCES research_requests(id) ON DELETE CASCADE,
    site_id    uuid NOT NULL REFERENCES unified_sites(id) ON DELETE CASCADE,
    basis      text NOT NULL,
    added_by   varchar(100) NOT NULL,
    added_at   timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (request_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_research_paper_sites_site ON research_paper_sites (site_id);

COMMENT ON TABLE research_paper_sites IS
    'Curated sites a public Theo paper treats (reviewed links, migration 0031). Read by the SSR '
    'site page (papers) and the paper page (sites); both show only public papers and curated sites.';
COMMENT ON COLUMN research_paper_sites.basis IS
    'What in the paper treats the site: a short paraphrase of the passage or picture.';

INSERT INTO research_paper_sites (request_id, site_id, basis, added_by)
SELECT r.id, u.id, v.basis, 'claude-opus-5-5 review 2026-10-20'
FROM (VALUES
    -- ancient-astronaut-artifact-claims-and-scholarly-rebuttals
    ('f48e477c-19c4-4343-9166-ee2ea6e7db01', 'cf614eac-2835-4d18-9904-13b9c47c1ed2', 'text: dating and readings of the Nazca Lines'),
    ('f48e477c-19c4-4343-9166-ee2ea6e7db01', '9b2cd3fd-9171-4862-a9a2-a2efe7aa4817', 'text and pictures: the Pakal sarcophagus lid of Palenque'),
    ('f48e477c-19c4-4343-9166-ee2ea6e7db01', '4770146e-aaa9-49ca-a35e-76ec91b5ea94', 'text: the Saqqara Bird, excavated at Saqqara'),
    ('f48e477c-19c4-4343-9166-ee2ea6e7db01', '6f759cf6-fe55-4567-b1d1-26b536e8352e', 'picture: Yaxchilan Lintel 15'),
    -- cargo-cults-and-uncontacted-peoples-in-comparative-perspective
    ('a00c4ee2-0162-4bfe-997f-72f7ac3457fc', 'f2de39f0-bf5a-4da0-8be0-d06bb65f1af2', 'text: Cholula, the Quetzalcoatl city that attacked Cortes'),
    -- cyclical-world-ages-in-comparative-mythology
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', '44def22f-dca7-4075-a555-d64821a0d882', 'text: Tortuguero Monument 6'),
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', '7b061e76-f20f-447d-9650-c334492b86dc', 'text: the Sun Stone in the National Museum of Anthropology'),
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', '9b2cd3fd-9171-4862-a9a2-a2efe7aa4817', 'text: the Temple of the Foliated Cross at Palenque'),
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', 'b622ebae-c26d-4aef-a028-15edc1596f02', 'pictures: Quirigua stelae'),
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', 'de42523e-9322-4dba-9448-016174872c48', 'text: the Fifth Sun inaugurated at Teotihuacan'),
    ('1d0053d4-c28b-45db-a30c-20c6501d6147', '47c3b2a4-e476-4d38-b390-280c136fd1c5', 'text: the Xultun astronomical tables'),
    -- flying-discs-in-european-religious-art
    ('1e7678ad-2e4b-4e6d-8353-701d38037c8e', '29440d54-9b26-4f92-9f0c-b7573373d12c', 'text: stereoscopic imaging at La Pasiega'),
    ('1e7678ad-2e4b-4e6d-8353-701d38037c8e', '9b2cd3fd-9171-4862-a9a2-a2efe7aa4817', 'text: the Pakal sarcophagus at Palenque'),
    -- geomagnetic-excursions-and-pole-shift-catastrophism
    ('a56973e7-19b2-4394-be43-24182ef4fb1a', 'd953e9b3-de33-4c7d-9357-bbc5d94d2a16', 'text: Pillar 43 of Gobekli Tepe'),
    -- hawaras-labyrinth-between-mainstream-and-fringe-archaeology
    ('994e7d40-e35d-49af-8af6-cfaef9e1279b', '9ef004b4-0fe9-48c5-9f93-d8476487bb6e', 'text: the pyramid of Amenemhat III at Hawara'),
    ('994e7d40-e35d-49af-8af6-cfaef9e1279b', '86aa32d3-94cb-4b60-a5f0-d6673219ee5e', 'text: the Labyrinth, Amenemhat III''s mortuary temple'),
    ('994e7d40-e35d-49af-8af6-cfaef9e1279b', '68ff480b-a02b-4458-b131-22dff4a00df6', 'text: the earlier Black Pyramid at Dahshur'),
    -- induced-emf-in-ancient-megalithic-stone-structures
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'cfaf38c0-0365-4841-a42a-1cfc5c45c42d', 'text: directional magnetism of the Puma Punku stones'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', '4c6ce4c1-8c8c-4982-a0fc-8df781a35ef6', 'text: the Avebury radiation test'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'd953e9b3-de33-4c7d-9357-bbc5d94d2a16', 'text: the magnetic anomaly between the central pillars'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', '3696e872-ce24-42c2-b632-fe7b034171df', 'picture: Structure AB of Karahan Tepe'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'e4f22a09-abfb-43d9-a7af-e87c033ae455', 'picture: the passage tomb chamber of Newgrange'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', '21b2278e-c3f2-4723-ae40-fa8a6161e3fb', 'text: electromagnetic induction surveys at Stonehenge'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'de42523e-9322-4dba-9448-016174872c48', 'text: field claims about the Pyramid of the Sun at Teotihuacan'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'a0f66e3c-744c-493c-8584-ad80194ee21d', 'text: field claims about the Pyramid of the Sun'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', '6313cd62-456d-4a85-8782-57613c7fc0e1', 'text: the ITMO multipole model of the Great Pyramid'),
    ('4886d748-c37f-4c09-8fc6-f29eef5caacb', 'f30145f9-4f34-4a4f-9553-5d42001da5a5', 'text: the 1983 magnetometer surveys at the Rollright stones'),
    -- the-squatter-man-petroglyph-and-auroral-sky-mythology
    ('27ec3538-258c-4960-9493-2bf6c0dc1a3b', 'd953e9b3-de33-4c7d-9357-bbc5d94d2a16', 'text: the T-pillars and carvings of Gobekli Tepe'),
    ('27ec3538-258c-4960-9493-2bf6c0dc1a3b', 'ffd325ad-d579-4510-90c7-acb87b753c88', 'text: Peratt on the Majorville Medicine Wheel'),
    ('27ec3538-258c-4960-9493-2bf6c0dc1a3b', '21b2278e-c3f2-4723-ae40-fa8a6161e3fb', 'text and picture: Peratt on Stonehenge'),
    -- the-egyptian-hard-stone-precision-debate
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', '50d4292b-caee-4819-8aaa-64b94187fce8', 'text: the granite boxes of the Serapeum'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', '4770146e-aaa9-49ca-a35e-76ec91b5ea94', 'text: the vaults beneath Saqqara'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', '6313cd62-456d-4a85-8782-57613c7fc0e1', 'text and pictures: Petrie''s measurements of the Great Pyramid'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', 'eff62515-9b70-43cc-afe6-c803dd4b5bc3', 'text and pictures: Petrie''s Giza survey'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', '2cabda2f-f7d3-4cc4-8346-7afcff7babcf', 'text: corundum residue from the Great Aten Temple drill cores'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', 'f4955fe7-d4e9-4de7-9812-0fc7e94c0620', 'text: the scoop marks of the unfinished obelisk at Aswan'),
    ('4bf89556-97e4-4c62-826d-d232b4b4de39', '2715f436-40ec-4225-b5b6-8cc9523b2048', 'text: the slope of the Bent Pyramid'),
    -- the-engineering-and-origins-of-the-baalbek-megaliths
    ('29436601-239b-4139-a5a0-c9e34e32928f', '0371ed0a-82f5-4578-b7bf-10dc40faf580', 'text: the sanctuary and the trilithon of Baalbek'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', 'be81c1a6-cd42-4fea-8bb9-323bf0a1c586', 'text: the Stone of the Pregnant Woman in its quarry'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', '8ee9e59b-a2fd-4a46-b3a6-a9ae4efc0500', 'text: the date of the Temple of Bacchus'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', '485c3c0c-31f0-45a7-a06b-797c4c021466', 'text: overland transport of the Menga dolmen stones'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', '5fc3dde6-5284-41ba-af51-d91420bd0299', 'picture: the Pont du Gard as Roman engineering'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', 'ba452543-f3d8-436b-bef5-4329382d234e', 'picture: the Herodian retaining wall in Jerusalem'),
    ('29436601-239b-4139-a5a0-c9e34e32928f', 'f4955fe7-d4e9-4de7-9812-0fc7e94c0620', 'picture: the unfinished obelisk at Aswan'),
    -- the-enuma-elish-tiamat-and-the-sitchin-nibiru-controversy
    ('30dfca0b-0ce9-4ab5-b093-05a0240758bc', '5cd47e05-c322-4510-b40f-c1f75072c147', 'text: Ea/Enki of Eridu and Eridu''s first-city prestige'),
    ('30dfca0b-0ce9-4ab5-b093-05a0240758bc', 'bad314d6-47c3-457f-ab77-9600fe9b04d2', 'text: the tablets recovered from the Library of Ashurbanipal'),
    ('30dfca0b-0ce9-4ab5-b093-05a0240758bc', '40e48fb3-769d-47c5-ac69-995bcd9e86b8', 'text: Marduk and the rise of Babylon'),
    -- the-watchers-nephilim-tradition-across-ancient-cultures
    ('64da0eaf-0528-46c2-be5b-b0e7d525167b', '45e548cc-858a-45cb-bc0e-a470c897a06c', 'text and pictures: the apkallu reliefs from Nimrud'),
    ('64da0eaf-0528-46c2-be5b-b0e7d525167b', '45c83a06-69a6-46f3-bb7a-eea482b9767c', 'picture: the Gigantomachy frieze of the Pergamon Altar'),
    -- the-lost-universal-tongue-in-myth-and-linguistics
    ('a98ad8fe-31e0-4abe-868e-02559f6c2c58', '40e48fb3-769d-47c5-ac69-995bcd9e86b8', 'text: the ziggurat of Marduk in Babylon'),
    ('a98ad8fe-31e0-4abe-868e-02559f6c2c58', '20851f57-93d5-4643-81ea-60aba5b58d9c', 'text and pictures: Etemenanki'),
    ('a98ad8fe-31e0-4abe-868e-02559f6c2c58', 'd0b9e72f-73a8-4671-a01f-5cafa6e53bf8', 'text: Enmerkar of Uruk and the tower'),
    -- sky-figures-in-rock-art-message-or-projection
    ('6c639144-47b7-4c71-b9e3-912d00733306', 'ad2b103b-1296-40b2-895d-98f7dc8558be', 'text and picture: the Bangudae carvings, the opening site'),
    ('6c639144-47b7-4c71-b9e3-912d00733306', '4824e3bd-0240-4e21-9292-f49e7aa6b7ee', 'text: Group E of Uaxactun as an observatory'),
    -- water-erosion-evidence-in-the-osiris-shaft
    ('ef52c194-e8c8-42a9-b317-e64a273f7780', 'c4d4863e-2344-49aa-8699-457d71985c96', 'text: the Osiris Shaft, the paper''s subject'),
    ('ef52c194-e8c8-42a9-b317-e64a273f7780', 'eff62515-9b70-43cc-afe6-c803dd4b5bc3', 'text: geomorphology of the Giza necropolis'),
    ('ef52c194-e8c8-42a9-b317-e64a273f7780', '4599daa4-93cc-4c55-872c-41e9c7875a59', 'text and pictures: water damage of the Sphinx'),
    ('ef52c194-e8c8-42a9-b317-e64a273f7780', '89489dc6-0f27-48bc-9365-5c74725b46dc', 'text and picture: the Khafre causeway and pyramid')
) AS v(request_id, site_id, basis)
JOIN research_requests r ON r.id = v.request_id::uuid
JOIN unified_sites u ON u.id = v.site_id::uuid
ON CONFLICT (request_id, site_id) DO NOTHING;
