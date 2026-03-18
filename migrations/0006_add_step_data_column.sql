-- Add step_data JSONB column to pipeline_heartbeats for per-step timing/error persistence
ALTER TABLE pipeline_heartbeats ADD COLUMN IF NOT EXISTS step_data JSONB;
