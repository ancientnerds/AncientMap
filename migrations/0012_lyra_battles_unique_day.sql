-- One Lyra battle per (user, tier, day) — cardgame integrity backlog 2026-08-06.
-- resolve_lyra_duel() had no row lock and no unique constraint, so two racing
-- challenges could both pass can_challenge_lyra() and double credits/XP/pack
-- rewards. The code now inserts the lyra_battles row BEFORE granting rewards;
-- this unique index makes the racing duplicate fail with an IntegrityError.
--
-- No partial WHERE clause is needed: lyra_battles stores ONLY Lyra battles
-- (PvP battles live in card_battles), so there is no battle_type/opponent
-- discriminator column to exclude.
--
-- played_at is TIMESTAMP WITHOUT TIME ZONE (server_default now()), so the
-- played_at::date cast is IMMUTABLE and valid in an index expression.

-- Pre-cleanup: delete same-day duplicates, keeping the earliest battle per
-- (user_id, lyra_tier, day). Ties on played_at are broken by id so exactly
-- one row survives per group.
DELETE FROM lyra_battles
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, lyra_tier, (played_at::date)
                   ORDER BY played_at, id
               ) AS rn
        FROM lyra_battles
    ) ranked
    WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_lyra_battles_user_tier_day
    ON lyra_battles (user_id, lyra_tier, (played_at::date));
