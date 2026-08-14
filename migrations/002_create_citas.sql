-- =============================================================================
-- 002_create_citas.sql
--
-- Appointment scheduling ("agenda de citas").
--
-- A cita is an INTENTION, not an order: the customer is booked for a date/time
-- before the vehicle physically arrives, and may never show up. The order is
-- only born at reception. Citas therefore live in their own table and `orders`
-- gains no columns; the one-way bridge is citas.converted_order_id (created
-- here, but nothing writes it yet -- the conversion write path is deferred).
--
-- Idempotent, matching 001's style: inline PK/CHECK, FKs in a guarded DO block,
-- CREATE INDEX IF NOT EXISTS, self-registered in schema_migrations.
--
-- RLS: enabled with ZERO policies (blanket deny). 001 does not contain the
-- ENABLE statements (RLS was turned on out-of-band in production), so this file
-- states it explicitly for the new table.
-- =============================================================================

CREATE TABLE IF NOT EXISTS citas (
    id                 uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id    uuid        NOT NULL,
    customer_id        uuid        NOT NULL,
    vehicle_id         uuid,
    scheduled_at       timestamptz NOT NULL,
    service_type       text,
    status             text        NOT NULL DEFAULT 'agendada'::text,
    converted_order_id uuid,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT citas_pkey PRIMARY KEY (id),
    CONSTRAINT citas_status_check CHECK ((status = ANY (ARRAY[
        'agendada'::text, 'confirmada'::text, 'cumplida'::text,
        'no_show'::text, 'cancelada'::text
    ])))
);

-- ---------------------------------------------------------------------------
-- FOREIGN KEYS (guarded for idempotency, matching 001)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'citas_organization_id_fkey' AND conrelid = 'public.citas'::regclass) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'citas_customer_id_fkey' AND conrelid = 'public.citas'::regclass) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'citas_vehicle_id_fkey' AND conrelid = 'public.citas'::regclass) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_vehicle_id_fkey
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'citas_converted_order_id_fkey' AND conrelid = 'public.citas'::regclass) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_converted_order_id_fkey
            FOREIGN KEY (converted_order_id) REFERENCES orders(id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------------------------
-- The calendar's only read pattern: one org, one date range, ordered by time.
CREATE INDEX IF NOT EXISTS idx_citas_org_scheduled ON citas USING btree (organization_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_citas_org_status    ON citas USING btree (organization_id, status);

-- ---------------------------------------------------------------------------
-- ROW LEVEL SECURITY: enabled, no policies => blanket deny for anon/authenticated.
-- The backend reads and writes this table with the service_role key only.
-- ---------------------------------------------------------------------------
ALTER TABLE citas ENABLE ROW LEVEL SECURITY;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('002_create_citas')
ON CONFLICT (version) DO NOTHING;
