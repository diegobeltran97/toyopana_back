-- =============================================================================
-- 004_whatsapp_inbound.sql
--
-- Foundation for the inbound WhatsApp webhook.
--
-- Three things, all additive:
--
--   1. Closes a live data leak. wa_conversations, wa_messages, order_items,
--      order_statuses and parts shipped with RLS DISABLED while the anon role
--      holds full SELECT/INSERT/UPDATE/DELETE grants. The anon key ships in the
--      frontend bundle by design (NEXT_PUBLIC_SUPABASE_ANON_KEY), so those five
--      tables are readable and writable by anyone holding it -- wa_messages is
--      the entire WhatsApp conversation history. The other 12 tables already
--      have RLS enabled with zero policies (blanket deny); these were missed.
--      Verified safe: the frontend never queries tables directly (no .from()
--      calls in frontend/src), it uses Supabase for auth only, and the backend
--      uses the service_role key which bypasses RLS.
--
--   2. whatsapp_events: raw provider payloads. Two jobs -- idempotency for
--      events that carry no message id (statuses), and reprocessing when
--      something downstream fails. UNIQUE (provider, provider_event_id) is what
--      makes a Whapi retry a no-op. process_status doubles as the work queue if
--      BackgroundTasks is ever outgrown.
--
--   3. customers.last_inbound_at: the 24h customer-service window. Without it,
--      a move to Meta/Twilio means every outbound message must be a template,
--      forever.
--
-- Idempotent, matching 001/002/003's style: inline PK/CHECK, FK in a guarded DO
-- block, CREATE INDEX IF NOT EXISTS, RLS enabled with zero policies, and
-- self-registered in schema_migrations.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Close the leak: blanket deny on the five tables that shipped without RLS.
-- ---------------------------------------------------------------------------
ALTER TABLE wa_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE wa_messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items      ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_statuses   ENABLE ROW LEVEL SECURITY;
ALTER TABLE parts            ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 2. Raw inbound events.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS whatsapp_events (
    id                uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id   uuid        NOT NULL,
    provider          text        NOT NULL,            -- 'whapi'
    provider_event_id text        NOT NULL,            -- message id, or status id
    event_type        text        NOT NULL,            -- 'message' | 'status' | 'unknown'
    raw_payload       jsonb       NOT NULL,
    received_at       timestamptz NOT NULL DEFAULT now(),
    processed_at      timestamptz,
    -- NULL until the background step starts; the work-queue column if a real
    -- worker ever replaces BackgroundTasks.
    process_status    text,                            -- 'pending' | 'done' | 'failed'
    process_error     text,
    CONSTRAINT whatsapp_events_pkey PRIMARY KEY (id),
    -- The idempotency key: a Whapi retry hits this and is answered 200 without
    -- reprocessing. Note wa_messages.wa_message_id UNIQUE already covers
    -- double-replies for events that HAVE a message id; this covers the rest.
    CONSTRAINT whatsapp_events_provider_event_unique
        UNIQUE (provider, provider_event_id),
    CONSTRAINT whatsapp_events_event_type_check
        CHECK (event_type = ANY (ARRAY['message'::text, 'status'::text, 'unknown'::text])),
    CONSTRAINT whatsapp_events_process_status_check
        CHECK (process_status IS NULL OR process_status = ANY (ARRAY['pending'::text, 'done'::text, 'failed'::text]))
);

-- FK in a guarded DO block, matching 001's pattern.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'whatsapp_events_organization_id_fkey'
          AND conrelid = 'public.whatsapp_events'::regclass
    ) THEN
        ALTER TABLE whatsapp_events ADD CONSTRAINT whatsapp_events_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Makes the 30-day retention DELETE cheap.
CREATE INDEX IF NOT EXISTS whatsapp_events_received_at_idx
    ON whatsapp_events (received_at);

ALTER TABLE whatsapp_events ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 3. The 24h customer-service window.
-- ---------------------------------------------------------------------------
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_inbound_at timestamptz;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('004_whatsapp_inbound')
ON CONFLICT (version) DO NOTHING;
