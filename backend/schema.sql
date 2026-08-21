-- Bill Wrangler Database Schema
-- Run this in the Supabase SQL Editor (Database > SQL Editor > New query)

-- ─────────────────────────────────────────────
-- Table: gmail_accounts
-- ─────────────────────────────────────────────
CREATE TABLE gmail_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  email TEXT NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  token_expiry TIMESTAMPTZ,
  last_scanned_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE gmail_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users access own gmail accounts"
  ON gmail_accounts FOR ALL
  USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- Table: billers
-- ─────────────────────────────────────────────
CREATE TABLE billers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  name TEXT NOT NULL,
  account_number TEXT,
  sender_email TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE billers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users access own billers"
  ON billers FOR ALL
  USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- Table: bills
-- ─────────────────────────────────────────────
CREATE TABLE bills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  biller_id UUID REFERENCES billers(id) ON DELETE CASCADE,
  gmail_account_id UUID REFERENCES gmail_accounts(id) ON DELETE CASCADE,
  email_message_id TEXT NOT NULL,
  subject TEXT,
  sender TEXT,
  date_received TIMESTAMPTZ,
  due_date DATE,
  amount_due NUMERIC(12, 2),
  currency TEXT DEFAULT 'CAD',
  amount_source TEXT CHECK (amount_source IN ('subject', 'body', 'attachment')),
  raw_extraction JSONB,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'ignored')),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON bills (user_id, due_date);
CREATE INDEX ON bills (email_message_id);

ALTER TABLE bills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users access own bills"
  ON bills FOR ALL
  USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- Table: scan_jobs
-- ─────────────────────────────────────────────
CREATE TABLE scan_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gmail_account_id UUID REFERENCES gmail_accounts(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  scan_type TEXT CHECK (scan_type IN ('initial', 'recurring')),
  started_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ,
  emails_scanned INT DEFAULT 0,
  bills_found INT DEFAULT 0,
  status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
  error TEXT
);

ALTER TABLE scan_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users access own scan jobs"
  ON scan_jobs FOR ALL
  USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- pg_cron setup (run AFTER deploying backend to Railway)
-- Requires pg_cron + pg_net extensions enabled in Supabase:
--   Database > Extensions > search "pg_cron" and "pg_net" > enable both
--
-- Then run:
--
-- SELECT cron.schedule(
--   'daily-bill-scan',
--   '0 6 * * *',
--   $$
--     SELECT net.http_post(
--       url := 'https://YOUR-RAILWAY-APP.railway.app/scan/recurring',
--       headers := '{"Authorization": "Bearer YOUR_CRON_SECRET"}'::jsonb
--     );
--   $$
-- );
-- ─────────────────────────────────────────────
