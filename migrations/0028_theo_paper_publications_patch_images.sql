-- 0028_theo_paper_publications_patch_images.sql
--
-- Rule 8 of docs/reports/theo-paper-defects-2026-10-04.md (class H.2):
-- `correct_paper` never writes `probative_images`, so a picture of a public
-- paper could only change through a full republish, which replaces the whole
-- stored text. The report measured 7 dead image URLs (511 references, 504 with
-- HTTP 200), and the fix has to be a patch path, not seven republications.
--
-- `patch_images` is its own journal action (pipeline/lyra/theo_publishing.py):
-- it writes the image list and swaps the replaced images' markdown blocks and
-- nothing else of the paper. A `correct` row would claim a text correction that
-- never happened, and the action's CHECK constraint would refuse the row
-- anyway.
--
-- WHY a new migration: the action vocabulary is a CHECK constraint, so the new
-- action is not writable until this has run. Forward-only and idempotent: both
-- statements are guarded with IF EXISTS / IF NOT EXISTS, so re-running it is a
-- no-op. The old constraint name is kept, so a rollback of the code alone (not
-- of the schema) leaves a superset vocabulary and no row becomes invalid.
--
-- LOCKING: ACCESS EXCLUSIVE on theo_paper_publications for the duration of two
-- catalog-only statements (a few hundred rows); no table rewrite.

BEGIN;

ALTER TABLE theo_paper_publications
    DROP CONSTRAINT IF EXISTS theo_paper_publications_action_vocab;

ALTER TABLE theo_paper_publications
    ADD CONSTRAINT theo_paper_publications_action_vocab
    CHECK (action IN ('publish', 'correct', 'register_video', 'patch_images'));

COMMENT ON TABLE theo_paper_publications IS
    'One row per write of the Claude publish path (publish, correct, '
    'register_video, patch_images): writer, input bundle hash, gate results and '
    'post-commit side effects (pipeline/lyra/theo_publishing.py).';

COMMIT;
