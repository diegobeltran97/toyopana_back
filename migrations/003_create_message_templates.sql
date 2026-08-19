-- =============================================================================
-- 003_create_message_templates.sql
--
-- User-authored WhatsApp message templates.
--
-- Order outreach is template-only: operators cannot send free-form WhatsApp
-- text. This table is where that copy lives, replacing the hardcoded registry
-- in app/integrations/messaging/templates.py.
--
-- Why templates and not free text: unofficial providers (Whapi) accept any
-- text, but official ones (Meta Cloud API, Twilio) require business-initiated
-- messages to reference PRE-APPROVED copy by name. provider_template_name and
-- approval_status are created here but nothing writes them yet -- they are the
-- bridge for that migration, same tactic as citas.converted_order_id in 002.
--
-- Idempotent, matching 001/002's style: inline PK/CHECK, FKs in a guarded DO
-- block, CREATE INDEX IF NOT EXISTS, self-registered in schema_migrations.
--
-- RLS: enabled with ZERO policies (blanket deny), matching citas. The backend
-- reads and writes with the service_role key only.
-- =============================================================================

CREATE TABLE IF NOT EXISTS message_templates (
    id                     uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id        uuid        NOT NULL,
    name                   text        NOT NULL,
    body                   text        NOT NULL,
    params                 text[]      NOT NULL DEFAULT ARRAY[]::text[],
    language               text        NOT NULL DEFAULT 'es'::text,
    -- Class B (Meta/Twilio) only: the approved template's name on their side.
    provider_template_name text,
    approval_status        text,
    is_active              boolean     NOT NULL DEFAULT true,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT message_templates_pkey PRIMARY KEY (id),
    -- The send path resolves a template by (org, name); it must be unique.
    CONSTRAINT message_templates_org_name_key UNIQUE (organization_id, name),
    CONSTRAINT message_templates_name_check CHECK (name <> ''),
    CONSTRAINT message_templates_body_check CHECK (body <> ''),
    CONSTRAINT message_templates_approval_status_check CHECK (
        approval_status IS NULL OR approval_status = ANY (ARRAY[
            'pending'::text, 'approved'::text, 'rejected'::text
        ])
    )
);

-- ---------------------------------------------------------------------------
-- FOREIGN KEYS (guarded for idempotency, matching 001/002)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'message_templates_organization_id_fkey' AND conrelid = 'public.message_templates'::regclass) THEN
        ALTER TABLE message_templates ADD CONSTRAINT message_templates_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------------------------
-- The only read patterns: list a org's templates, and resolve one by name
-- (the latter is already served by the UNIQUE constraint above).
CREATE INDEX IF NOT EXISTS idx_message_templates_org_active
    ON message_templates USING btree (organization_id, is_active);

-- ---------------------------------------------------------------------------
-- SEED: carry over the copy that was hardcoded in whapify_service.py, for
-- every existing organization, so the send flow keeps working unchanged.
-- ---------------------------------------------------------------------------
INSERT INTO message_templates (organization_id, name, body, params, language)
SELECT
    o.id,
    'delivery_notification',
    $tpl$Hola {customer_name}, ¿cómo estás?

Te escribimos porque tienes una cotización pendiente con nosotros para tu {car_info}.

En este momento puedes aprovechar el beneficio de pagar con tarjeta BAC o St. George Bank hasta un plazo de 12 meses sin intereses.

Si deseas retomar el trabajo o agendar tu cita, estamos disponibles para ayudarte.$tpl$,
    ARRAY['customer_name', 'car_info']::text[],
    'es'
FROM organization o
ON CONFLICT (organization_id, name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- ROW LEVEL SECURITY: enabled, no policies => blanket deny for anon/authenticated.
-- ---------------------------------------------------------------------------
ALTER TABLE message_templates ENABLE ROW LEVEL SECURITY;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('003_create_message_templates')
ON CONFLICT (version) DO NOTHING;
