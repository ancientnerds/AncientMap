-- BLOCK 10: Millennium (ml. BC) pattern fixes
-- Parses raw_data->>'year' patterns like "9th ml. BC", "4th - 2nd ml. BC", etc.
-- into correct period_start values.
-- Applied: 2026-02-15

BEGIN;

-- Group 1: Simple "Nth ml. BC" (e.g. "1st ml. BC" → -1000, "9th ml. BC" → -9000)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000 < -500 THEN '1500 - 500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '(st|nd|rd|th) ml\. BC', ''))::int * 1000 < 1 THEN '500 BC - 1 AD'
      ELSE '1 - 500 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th) ml\. BC$';

-- Group 2: Range "Xth - Yth ml. BC" (e.g. "4th - 2nd ml. BC" → use earlier, -4000)
-- Extract first number (the earlier/larger millennium)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -500 THEN '1500 - 500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < 1 THEN '500 BC - 1 AD'
      ELSE '1 - 500 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th)\s*-\s*[0-9]+(st|nd|rd|th) ml\. BC$';

-- Group 2b: Variant with space before "nd" like "4th - 2 nd ml. BC"
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+\s*(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+\s*(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+\s*(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+\s*(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th)\s*-\s*[0-9]+\s*(st|nd|rd|th) ml\. BC$', '\1'))::int * 1000 < -500 THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th)\s*-\s*[0-9]+\s+(st|nd|rd|th) ml\. BC$';

-- Group 3: "Nth ml. BC - Mth c. AD" cross-era ranges (use the BC millennium as start)
-- e.g. "2nd ml. BC - 7th c. AD" → -2000
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$', '\1'))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$', '\1'))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$', '\1'))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$', '\1'))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$', '\1'))::int * 1000 < -500 THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) c\. AD$';

-- Group 4: "Nth ml. BC - Mth c. BC" (millennium to century, both BC)
-- e.g. "6th ml. - 12th c. BC" → -6000, "2nd ml. - 8th c. BC" → -2000
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$', '\1'))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$', '\1'))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$', '\1'))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$', '\1'))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$', '\1'))::int * 1000 < -500 THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th) ml\.\s*-\s*[0-9]+(st|nd|rd|th) c\. BC$';

-- Group 5: "Nth ml. BC - Mth ml. AD" (e.g. "1st ml. BC - 1st ml. AD" → -1000)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$', '\1'))::int * 1000,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$', '\1'))::int * 1000 < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$', '\1'))::int * 1000 < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$', '\1'))::int * 1000 < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', '^([0-9]+)(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$', '\1'))::int * 1000 < -500 THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' ~ '^[0-9]+(st|nd|rd|th) ml\. BC\s*-\s*[0-9]+(st|nd|rd|th) ml\. AD$';

-- Group 6: "Nth ml. BC - Xth c. AD" with longer century numbers (e.g. "1st ml. BC - 15th c. AD")
-- Already covered by Group 3 regex (handles any number of digits)

-- Group 7: "5th ml. BC - 100 AD" (specific AD year, not century)
UPDATE unified_sites
SET period_start = -5000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '5th ml. BC - 100 AD';

-- Group 8: "Xth - Yth ml. BC" with various spacing issues (e.g. "8th -2nd ml. BC", "35 th ml. BC")
-- "35 th ml. BC" special case
UPDATE unified_sites
SET period_start = -35000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '35 th ml. BC';

-- "8th -2nd ml. BC" (no space after dash)
UPDATE unified_sites
SET period_start = -8000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '8th -2nd ml. BC';

-- "8th - 2 ml. BC" (missing ordinal suffix on second number)
UPDATE unified_sites
SET period_start = -8000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '8th - 2 ml. BC';

-- "1st. ml. BC - 5th c. AD" (extra period after 1st)
UPDATE unified_sites
SET period_start = -1000, period_name = '1500 - 500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '1st. ml. BC - 5th c. AD';

-- Group 9: "Nth ml. BC - Xth c. AD" with large century numbers (e.g. "4th ml. BC - 17th c. AD", "18th ml. BC - 20th c. AD")
-- Already covered by Group 3

-- Group 10: "Xth ml. BC - Nth c. AD" special patterns
-- "12th ml. BC - 5th c. AD" → -12000
UPDATE unified_sites
SET period_start = -12000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '12th ml. BC - 5th c. AD';

-- "6th ml. BC - 3rd c. AD" → -6000
UPDATE unified_sites
SET period_start = -6000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '6th ml. BC - 3rd c. AD';

-- "6th ml. BC - 7th c. AD" → -6000
UPDATE unified_sites
SET period_start = -6000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '6th ml. BC - 7th c. AD';

-- "6th ml. BC - 17th c. AD" → -6000
UPDATE unified_sites
SET period_start = -6000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '6th ml. BC - 17th c. AD';

-- "5th ml. BC - 10th c. AD" → -5000
UPDATE unified_sites
SET period_start = -5000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '5th ml. BC - 10th c. AD';

-- "5th ml. BC - 1st c. AD" → -5000
UPDATE unified_sites
SET period_start = -5000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '5th ml. BC - 1st c. AD';

-- "4th ml. BC - 7th c. AD" → -4000
UPDATE unified_sites
SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '4th ml. BC - 7th c. AD';

-- "4th ml. BC - 1st c. AD" → -4000
UPDATE unified_sites
SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '4th ml. BC - 1st c. AD';

-- "4th ml. BC - 15th c. AD" → -4000
UPDATE unified_sites
SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '4th ml. BC - 15th c. AD';

-- "4th ml. BC - 17th c. AD" → -4000
UPDATE unified_sites
SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '4th ml. BC - 17th c. AD';

-- "3rd ml. - 1st c. BC" → -3000
UPDATE unified_sites
SET period_start = -3000, period_name = '4500 - 3000 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '3rd ml. - 1st c. BC';

-- "18th ml. BC - 20th c. AD" → -18000
UPDATE unified_sites
SET period_start = -18000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND raw_data->>'year' = '18th ml. BC - 20th c. AD';

COMMIT;
