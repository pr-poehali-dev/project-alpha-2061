ALTER TABLE submissions
  ADD COLUMN IF NOT EXISTS telegram_contact VARCHAR(255),
  ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT,
  ADD COLUMN IF NOT EXISTS generated_content JSONB,
  ADD COLUMN IF NOT EXISTS reference_thumbnail_url TEXT;
