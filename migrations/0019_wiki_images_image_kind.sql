-- 0019_wiki_images_image_kind.sql
--
-- Add wiki_images.image_kind: what an image actually shows, as judged by a vision model.
--
-- WHY THIS FILE EXISTS
-- Plan §6.5 (gallery-audit stages) and Phase 2 item 3 require a per-image kind so that
-- non-photos stop reaching the site page and the shorts selector. Measured basis
-- (output/remediation/t10_scratch/REPORT.md, T10): of 49,691 curated images, 10,705 are
-- "clear" from metadata alone and the remaining 38,986 can only be settled by looking at
-- them. The word-signal route does not substitute for looking: signal E detects only
-- about 10 % of non-photos (recall 10.1 %, plan §6.4), so a kind inferred from
-- title/filename text would be worse than no value at all.
--
-- The vocabulary is the one the project's existing VLM prompt already produces
-- (pipeline/video/shorts_select.py:51-75):
--
--     site_photo | artifact | map_or_document | painting_or_artwork | people | other | unknown
--
-- NULL IS NOT 'unknown'. This distinction is the point of allowing NULL at all.
--   NULL      = no verdict has ever been recorded for this row (initially all 49,691)
--   'unknown' = a vision model looked at this image and could not decide
-- Back-filling the existing rows to 'unknown' would assert a judgement that never
-- happened, which is exactly the failure this project forbids: "could not check" must
-- never read as "checked and clean". Equally, only `image_kind = 'site_photo'` may ever
-- count as clean - NULL and 'unknown' are both not-clean.
--
-- The CHECK constraint is deliberate rather than a convention: an out-of-vocabulary value
-- must be impossible, not merely discouraged, because a typo'd kind ('site_photos') would
-- otherwise read as "not site_photo" and silently exclude a good image from every
-- downstream query.
--
-- No allowlist change is needed: the allowlist in 0017 is a list of TABLE names
-- (0017_remediation_change_log.sql:85 - 'unified_sites', 'card_stats', 'wiki_images'), not
-- of table/column pairs, so wiki_images is already permitted for any column. Verified by
-- reading 0017, not assumed.
--
-- Restart behaviour: survives. FIELD_CONTRACT §2 names exactly three boot-time
-- overwriters (unified_sites.site_type, unified_sites.name_normalized,
-- card_stats.card_description); none touches wiki_images, matching the wave-2 finding that
-- wiki_images.is_hero has no restart writer. A future boot-time producer for wiki_images
-- would invalidate this and must be caught by the contract, not by luck.
--
-- Forward-only and idempotent: ADD COLUMN IF NOT EXISTS plus a DO block that creates the
-- constraint only when absent, so the deploy job re-applying this file is harmless.
--
-- Adding a nullable column with no DEFAULT does not rewrite the table - it is a catalog
-- change only, so this is cheap on a 49,691-row table and takes its lock briefly.

BEGIN;

ALTER TABLE wiki_images
    ADD COLUMN IF NOT EXISTS image_kind TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'wiki_images'::regclass
           AND conname  = 'wiki_images_image_kind_vocab'
    ) THEN
        ALTER TABLE wiki_images
            ADD CONSTRAINT wiki_images_image_kind_vocab
            CHECK (
                image_kind IS NULL
                OR image_kind IN (
                    'site_photo',
                    'artifact',
                    'map_or_document',
                    'painting_or_artwork',
                    'people',
                    'other',
                    'unknown'
                )
            );
    END IF;
END
$$;

COMMENT ON COLUMN wiki_images.image_kind IS
    'What the image shows, judged by a vision model. NULL = never judged; unknown = judged '
    'and undecidable. Only ''site_photo'' may count as clean. Written exclusively through '
    'apply_remediation_change() so every change is journalled and reversible.';

-- Prove the constraint can fail before trusting it. The first draft of this block was a check
-- that could not fail: it wrote `WHERE false`, which touches zero rows, so the CHECK was never
-- evaluated, and the following RAISE EXCEPTION is a `raise_exception` that the
-- `WHEN check_violation` handler does not catch - so it aborted the migration every single time.
-- Writing to one real row inside a subtransaction is what gives this teeth: if the constraint is
-- missing the UPDATE succeeds, the RAISE fires, the handler does not catch it, and the migration
-- aborts loudly instead of shipping an unconstrained column.
DO $$
DECLARE
    v_id BIGINT;
    v_after TEXT;
BEGIN
    SELECT id INTO v_id FROM wiki_images LIMIT 1;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'SELFTEST FAILED: wiki_images is empty, the vocabulary check is untested';
    END IF;

    BEGIN
        UPDATE wiki_images SET image_kind = 'not_a_kind' WHERE id = v_id;
        RAISE EXCEPTION 'SELFTEST FAILED: the vocabulary check accepted an invalid value';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'selftest: vocabulary check refuses invalid values (teeth confirmed)';
    END;

    -- The rejected subtransaction rolled back, so the row must still be untouched.
    SELECT image_kind INTO v_after FROM wiki_images WHERE id = v_id;
    IF v_after IS NOT NULL THEN
        RAISE EXCEPTION 'SELFTEST FAILED: a rejected value was stored anyway (%)', v_after;
    END IF;
END
$$;

COMMIT;
