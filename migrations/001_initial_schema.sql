-- =============================================================================
-- 001_initial_schema.sql
--
-- Baseline DDL for the `public` schema of the Toyopana OPS database.
-- Reconstructed by read-only introspection of the PRODUCTION database via the
-- Postgres system catalogs (information_schema / pg_catalog).
--
-- Source project ID : gkekhqbsnknuyfaixtkf
-- Generated (UTC)   : 2026-07-19
--
-- Idempotent: safe to run repeatedly.
--   * Tables use CREATE TABLE IF NOT EXISTS (PK / UNIQUE / CHECK constraints
--     are declared inline).
--   * Foreign keys are added afterwards as guarded ALTER TABLE statements so
--     table ordering can never break the load.
--   * Indexes use CREATE INDEX IF NOT EXISTS.
--
-- Not reconstructed: Supabase-internal schemas are never CREATED here (auth,
--   storage, extensions, realtime, vault); no ownership/GRANT statements; no
--   session SET statements.
--
-- NOTE: two objects reference the `auth` schema exactly where production depends
--   on it — the FK app_users.id -> auth.users(id) and the signup trigger
--   `on_auth_user_created` on auth.users. Both ARE emitted, each guarded so they
--   apply only when the auth schema is present (real Supabase project) and are
--   skipped cleanly on a plain Postgres.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions required by the DDL
-- ---------------------------------------------------------------------------
-- gen_random_uuid() is used as a column default across most tables. It is
-- built into Postgres core (>=13) and also provided by pgcrypto. This guard is
-- a no-op if pgcrypto already exists (it does in this project).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Sequences owned by serial columns
-- ---------------------------------------------------------------------------
-- card_actions.id is a serial column; recreate its backing sequence explicitly
-- so the column default resolves. (No standalone/un-owned sequences exist.)
CREATE SEQUENCE IF NOT EXISTS card_actions_id_seq;

-- ===========================================================================
-- TABLES (in dependency order: referenced tables before referencing tables)
-- ===========================================================================

-- --- organization -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS organization (
    id                uuid        NOT NULL DEFAULT gen_random_uuid(),
    name              text        NOT NULL,
    legal_name        text,
    tax_id            text,
    created_at        timestamp   DEFAULT now(),
    updated_at        timestamptz DEFAULT now(),
    slug              text,
    logo_url          text,
    whapi_token       text,
    whapi_phone       text,
    subscription_plan text        NOT NULL DEFAULT 'basic'::text,
    features_enabled  jsonb       NOT NULL DEFAULT '["orders", "whatsapp_bot"]'::jsonb,
    CONSTRAINT organization_pkey PRIMARY KEY (id),
    CONSTRAINT organization_slug_key UNIQUE (slug)
);

-- --- order_statuses ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_statuses (
    id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    status_type text        NOT NULL,
    code        text        NOT NULL,
    label       text        NOT NULL,
    sort_order  integer     NOT NULL,
    is_terminal boolean     NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT order_statuses_pkey PRIMARY KEY (id),
    CONSTRAINT order_statuses_code_key UNIQUE (code)
);

-- --- card_actions ------------------------------------------------------------
-- Quirk (preserved to match production): organization_id here is
-- `character varying` with NO foreign key, unlike every other table where it is
-- a uuid FK to organization. The existing data is in fact valid org uuids that
-- resolve to organization, so this could later be migrated to uuid + FK via a
-- separate forward migration if desired.
CREATE TABLE IF NOT EXISTS card_actions (
    id              integer            NOT NULL DEFAULT nextval('card_actions_id_seq'::regclass),
    organization_id character varying  NOT NULL,
    pipefy_card_id  character varying  NOT NULL,
    action_type     character varying  NOT NULL,
    action_context  jsonb,
    status          character varying  DEFAULT 'completed'::character varying,
    error_message   text,
    performed_at    timestamp          DEFAULT now(),
    CONSTRAINT card_actions_pkey PRIMARY KEY (id),
    CONSTRAINT card_actions_organization_id_pipefy_card_id_action_type_act_key
        UNIQUE (organization_id, pipefy_card_id, action_type, action_context)
);
ALTER SEQUENCE card_actions_id_seq OWNED BY card_actions.id;

-- --- pipefy_events_backup ----------------------------------------------------
-- Backup table: has NO primary key and NO constraints in production. Preserved
-- as-is (bare column set).
CREATE TABLE IF NOT EXISTS pipefy_events_backup (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid        NOT NULL,
    pipefy_card_id  text,
    pipe_id         text,
    event_type      text,
    raw_payload     jsonb       NOT NULL,
    created_at      timestamptz DEFAULT now(),
    actions_taken   json
);

-- --- app_users ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_users (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid        NOT NULL,
    name            text        NOT NULL,
    email           text        NOT NULL,
    role            text        NOT NULL DEFAULT 'admin'::text,
    created_at      timestamptz DEFAULT now(),
    phone           text,
    address         text,
    auth_uid        text,
    CONSTRAINT app_users_pkey PRIMARY KEY (id),
    CONSTRAINT app_users_auth_uid_key UNIQUE (auth_uid),
    CONSTRAINT app_users_email_key UNIQUE (email)
);

-- --- customers ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid        NOT NULL,
    type            text        NOT NULL DEFAULT 'individual'::text,
    name            text        NOT NULL,
    phone           text,
    whatsapp_id     text,
    source          text        DEFAULT 'manual'::text,
    created_at      timestamptz DEFAULT now(),
    last_contact_at timestamptz DEFAULT now(),
    national_id     text,
    CONSTRAINT customers_pkey PRIMARY KEY (id),
    CONSTRAINT customers_type_check CHECK ((type = ANY (ARRAY['individual'::text, 'business'::text])))
);

-- --- vehicles ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicles (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    make            text        NOT NULL,
    model           text        NOT NULL,
    year            integer,
    plate           text,
    km_last_service integer     DEFAULT 0,
    updated_at      timestamptz DEFAULT now(),
    organization_id uuid,
    CONSTRAINT vehicles_pkey PRIMARY KEY (id),
    CONSTRAINT vehicles_plate_org_unique UNIQUE (plate, organization_id)
);

-- --- parts -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parts (
    id              uuid           NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid           NOT NULL,
    sku             text,
    name            text           NOT NULL,
    brand           text,
    cost            numeric(10,2)  DEFAULT 0.00,
    price           numeric(10,2)  DEFAULT 0.00,
    stock           integer        NOT NULL DEFAULT 0,
    stock_min       integer        NOT NULL DEFAULT 0,
    CONSTRAINT parts_pkey PRIMARY KEY (id)
);

-- --- field_definitions -------------------------------------------------------
CREATE TABLE IF NOT EXISTS field_definitions (
    id              uuid    NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid    NOT NULL,
    service_type    text,
    field_name      text    NOT NULL,
    field_type      text    NOT NULL,
    field_options   jsonb,
    required        boolean NOT NULL DEFAULT false,
    display_order   integer NOT NULL DEFAULT 0,
    CONSTRAINT field_definitions_pkey PRIMARY KEY (id),
    CONSTRAINT field_definitions_field_type_check
        CHECK ((field_type = ANY (ARRAY['text'::text, 'text_field'::text, 'dropdown'::text, 'checkbox'::text, 'radio_button'::text])))
);

-- --- pipefy_events -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipefy_events (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid        NOT NULL,
    pipefy_card_id  text,
    pipe_id         text,
    event_type      text,
    raw_payload     jsonb       NOT NULL,
    created_at      timestamptz DEFAULT now(),
    actions_taken   json,
    CONSTRAINT pipefy_events_pkey PRIMARY KEY (id)
);

-- --- orders ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id              uuid          NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid          NOT NULL,
    customer_id     uuid          NOT NULL,
    vehicle_id      uuid,
    assigned_to     uuid,
    created_by      uuid,
    service_type    text          NOT NULL,
    order_status    text          NOT NULL DEFAULT 'recibido'::text,
    priority        text          NOT NULL DEFAULT 'media'::text,
    order_reason    text,
    total_amount    numeric(10,2) DEFAULT 0.00,
    received_at     timestamptz   DEFAULT now(),
    completed_at    timestamptz,
    date_order      timestamptz   DEFAULT now(),
    km_in           integer,
    order_comments  text,
    CONSTRAINT orders_pkey PRIMARY KEY (id),
    CONSTRAINT orders_priority_check CHECK ((priority = ANY (ARRAY['alta'::text, 'media'::text, 'baja'::text])))
);

-- --- order_items -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id          uuid          NOT NULL DEFAULT gen_random_uuid(),
    order_id    uuid          NOT NULL,
    part_id     uuid,
    description text          NOT NULL,
    qty         integer       NOT NULL DEFAULT 1,
    unit_price  numeric(10,2) NOT NULL DEFAULT 0.00,
    subtotal    numeric(10,2),
    CONSTRAINT order_items_pkey PRIMARY KEY (id)
);

-- --- order_files -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_files (
    id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    order_id    uuid        NOT NULL,
    uploaded_by uuid,
    file_url    text        NOT NULL,
    file_type   text,
    label       text,
    uploaded_at timestamptz DEFAULT now(),
    CONSTRAINT order_files_pkey PRIMARY KEY (id)
);

-- --- order_field_values ------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_field_values (
    id                  uuid NOT NULL DEFAULT gen_random_uuid(),
    order_id            uuid NOT NULL,
    field_definition_id uuid NOT NULL,
    value               text,
    CONSTRAINT order_field_values_pkey PRIMARY KEY (id),
    CONSTRAINT order_field_values_order_id_field_definition_id_key UNIQUE (order_id, field_definition_id)
);

-- --- order_status_history ----------------------------------------------------
CREATE TABLE IF NOT EXISTS order_status_history (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    order_id        uuid        NOT NULL,
    organization_id uuid        NOT NULL,
    status_type     text        NOT NULL,
    from_status     text,
    to_status       text        NOT NULL,
    changed_by      uuid,
    changed_at      timestamptz NOT NULL DEFAULT now(),
    notes           text,
    CONSTRAINT order_status_history_pkey PRIMARY KEY (id),
    CONSTRAINT order_status_history_status_type_check
        CHECK ((status_type = ANY (ARRAY['workshop'::text, 'followup'::text])))
);

-- --- wa_conversations --------------------------------------------------------
CREATE TABLE IF NOT EXISTS wa_conversations (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    organization_id uuid        NOT NULL,
    customer_id     uuid,
    wa_chat_id      text        NOT NULL,
    status          text        NOT NULL DEFAULT 'bot'::text,
    assigned_to     uuid,
    last_message_at timestamptz DEFAULT now(),
    CONSTRAINT wa_conversations_pkey PRIMARY KEY (id),
    CONSTRAINT wa_conversations_status_check
        CHECK ((status = ANY (ARRAY['bot'::text, 'waiting'::text, 'agent'::text, 'resolved'::text]))),
    CONSTRAINT wa_conversations_organization_id_wa_chat_id_key UNIQUE (organization_id, wa_chat_id)
);

-- --- wa_messages -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wa_messages (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    conversation_id uuid        NOT NULL,
    direction       text        NOT NULL,
    wa_message_id   text,
    body            text,
    media_url       text,
    status          text        DEFAULT 'sent'::text,
    sent_at         timestamptz DEFAULT now(),
    CONSTRAINT wa_messages_pkey PRIMARY KEY (id),
    CONSTRAINT wa_messages_direction_check CHECK ((direction = ANY (ARRAY['inbound'::text, 'outbound'::text]))),
    CONSTRAINT wa_messages_wa_message_id_key UNIQUE (wa_message_id)
);

-- ===========================================================================
-- FOREIGN KEYS (added after all tables; each guarded for idempotency)
-- ===========================================================================
DO $$
BEGIN
    -- app_users
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_users_organization_id_fkey' AND conrelid = 'public.app_users'::regclass) THEN
        ALTER TABLE app_users ADD CONSTRAINT app_users_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- customers
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'customers_organization_id_fkey' AND conrelid = 'public.customers'::regclass) THEN
        ALTER TABLE customers ADD CONSTRAINT customers_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- vehicles
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vehicles_organization_id_fkey' AND conrelid = 'public.vehicles'::regclass) THEN
        ALTER TABLE vehicles ADD CONSTRAINT vehicles_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- parts
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'parts_organization_id_fkey' AND conrelid = 'public.parts'::regclass) THEN
        ALTER TABLE parts ADD CONSTRAINT parts_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- field_definitions
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'field_definitions_organization_id_fkey' AND conrelid = 'public.field_definitions'::regclass) THEN
        ALTER TABLE field_definitions ADD CONSTRAINT field_definitions_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- pipefy_events
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pipefy_events_organization_id_fkey' AND conrelid = 'public.pipefy_events'::regclass) THEN
        ALTER TABLE pipefy_events ADD CONSTRAINT pipefy_events_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- orders
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_organization_id_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_customer_id_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_vehicle_id_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_vehicle_id_fkey
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_assigned_to_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_assigned_to_fkey
            FOREIGN KEY (assigned_to) REFERENCES app_users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_created_by_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES app_users(id);
    END IF;
    -- NB: legacy constraint name (order_status was once `workshop_status`);
    -- kept as-is to match production.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_workshop_status_fkey' AND conrelid = 'public.orders'::regclass) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_workshop_status_fkey
            FOREIGN KEY (order_status) REFERENCES order_statuses(code) ON UPDATE CASCADE;
    END IF;

    -- order_items
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_items_order_id_fkey' AND conrelid = 'public.order_items'::regclass) THEN
        ALTER TABLE order_items ADD CONSTRAINT order_items_order_id_fkey
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_items_part_id_fkey' AND conrelid = 'public.order_items'::regclass) THEN
        ALTER TABLE order_items ADD CONSTRAINT order_items_part_id_fkey
            FOREIGN KEY (part_id) REFERENCES parts(id);
    END IF;

    -- order_files
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_files_order_id_fkey' AND conrelid = 'public.order_files'::regclass) THEN
        ALTER TABLE order_files ADD CONSTRAINT order_files_order_id_fkey
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_files_uploaded_by_fkey' AND conrelid = 'public.order_files'::regclass) THEN
        ALTER TABLE order_files ADD CONSTRAINT order_files_uploaded_by_fkey
            FOREIGN KEY (uploaded_by) REFERENCES app_users(id);
    END IF;

    -- order_field_values
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_field_values_order_id_fkey' AND conrelid = 'public.order_field_values'::regclass) THEN
        ALTER TABLE order_field_values ADD CONSTRAINT order_field_values_order_id_fkey
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_field_values_field_definition_id_fkey' AND conrelid = 'public.order_field_values'::regclass) THEN
        ALTER TABLE order_field_values ADD CONSTRAINT order_field_values_field_definition_id_fkey
            FOREIGN KEY (field_definition_id) REFERENCES field_definitions(id);
    END IF;

    -- order_status_history
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_status_history_order_id_fkey' AND conrelid = 'public.order_status_history'::regclass) THEN
        ALTER TABLE order_status_history ADD CONSTRAINT order_status_history_order_id_fkey
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_status_history_organization_id_fkey' AND conrelid = 'public.order_status_history'::regclass) THEN
        ALTER TABLE order_status_history ADD CONSTRAINT order_status_history_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_status_history_changed_by_fkey' AND conrelid = 'public.order_status_history'::regclass) THEN
        ALTER TABLE order_status_history ADD CONSTRAINT order_status_history_changed_by_fkey
            FOREIGN KEY (changed_by) REFERENCES app_users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_status_history_from_status_fkey' AND conrelid = 'public.order_status_history'::regclass) THEN
        ALTER TABLE order_status_history ADD CONSTRAINT order_status_history_from_status_fkey
            FOREIGN KEY (from_status) REFERENCES order_statuses(code) ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_status_history_to_status_fkey' AND conrelid = 'public.order_status_history'::regclass) THEN
        ALTER TABLE order_status_history ADD CONSTRAINT order_status_history_to_status_fkey
            FOREIGN KEY (to_status) REFERENCES order_statuses(code) ON UPDATE CASCADE;
    END IF;

    -- wa_conversations
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'wa_conversations_organization_id_fkey' AND conrelid = 'public.wa_conversations'::regclass) THEN
        ALTER TABLE wa_conversations ADD CONSTRAINT wa_conversations_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'wa_conversations_customer_id_fkey' AND conrelid = 'public.wa_conversations'::regclass) THEN
        ALTER TABLE wa_conversations ADD CONSTRAINT wa_conversations_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'wa_conversations_assigned_to_fkey' AND conrelid = 'public.wa_conversations'::regclass) THEN
        ALTER TABLE wa_conversations ADD CONSTRAINT wa_conversations_assigned_to_fkey
            FOREIGN KEY (assigned_to) REFERENCES app_users(id);
    END IF;

    -- wa_messages
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'wa_messages_conversation_id_fkey' AND conrelid = 'public.wa_messages'::regclass) THEN
        ALTER TABLE wa_messages ADD CONSTRAINT wa_messages_conversation_id_fkey
            FOREIGN KEY (conversation_id) REFERENCES wa_conversations(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- app_users.id -> auth.users(id)
-- Supabase pattern: each app_users row is keyed by its auth user id. auth.users
-- is provisioned by Supabase before this migration runs; the guard also checks
-- the auth schema exists so the file stays safe on a plain Postgres.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'auth' AND table_name = 'users')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conname = 'app_users_id_fkey'
                         AND conrelid = 'public.app_users'::regclass) THEN
        ALTER TABLE app_users ADD CONSTRAINT app_users_id_fkey
            FOREIGN KEY (id) REFERENCES auth.users(id);
    END IF;
END $$;

-- ===========================================================================
-- INDEXES (non-PK / non-unique only; unique & PK indexes come with the
-- constraints declared above)
-- ===========================================================================
CREATE INDEX IF NOT EXISTS idx_card_actions_context  ON card_actions USING gin (action_context);
CREATE INDEX IF NOT EXISTS idx_card_actions_org      ON card_actions USING btree (organization_id);
CREATE INDEX IF NOT EXISTS idx_card_actions_org_card ON card_actions USING btree (organization_id, pipefy_card_id);
CREATE INDEX IF NOT EXISTS idx_card_actions_status   ON card_actions USING btree (status);
CREATE INDEX IF NOT EXISTS idx_card_actions_type     ON card_actions USING btree (action_type);

CREATE INDEX IF NOT EXISTS idx_customers_org   ON customers USING btree (organization_id);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers USING btree (phone);
CREATE INDEX IF NOT EXISTS idx_customers_wa    ON customers USING btree (whatsapp_id);

CREATE INDEX IF NOT EXISTS idx_field_def_org ON field_definitions USING btree (organization_id, service_type);

CREATE INDEX IF NOT EXISTS idx_ofv_order ON order_field_values USING btree (order_id);

CREATE INDEX IF NOT EXISTS idx_order_items_ord ON order_items USING btree (order_id);

CREATE INDEX IF NOT EXISTS idx_orders_assigned ON orders USING btree (assigned_to);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders USING btree (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_org      ON orders USING btree (organization_id);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders USING btree (order_status);

CREATE INDEX IF NOT EXISTS idx_parts_org ON parts USING btree (organization_id);

CREATE INDEX IF NOT EXISTS idx_wa_conv_cust ON wa_conversations USING btree (customer_id);
CREATE INDEX IF NOT EXISTS idx_wa_conv_org  ON wa_conversations USING btree (organization_id);

CREATE INDEX IF NOT EXISTS idx_wa_msg_conv ON wa_messages USING btree (conversation_id);

-- ===========================================================================
-- FUNCTIONS
-- ===========================================================================
-- public.handle_new_user() is a Supabase auth signup handler: on each new
-- auth.users row it inserts the matching public.app_users row. CREATE OR REPLACE
-- is idempotent. Its trigger (on auth.users) is emitted just below, guarded so
-- it only applies when the auth schema is present.
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_org_id uuid;
  v_name text;
  v_phone text;
  v_address text;
BEGIN
  -- Extract metadata from the signup request
  v_name := NEW.raw_user_meta_data ->> 'name';
  v_phone := NEW.raw_user_meta_data ->> 'phone';
  v_address := NEW.raw_user_meta_data ->> 'address';
  v_org_id := (NEW.raw_user_meta_data ->> 'organization_id')::uuid;

  -- If no org_id provided in metadata, use the hardcoded toyopanatest org
  IF v_org_id IS NULL THEN
    SELECT id INTO v_org_id FROM public.organization WHERE name = 'toyopanatest' LIMIT 1;
  END IF;

  -- Insert into app_users
  INSERT INTO public.app_users (id, organization_id, name, email, role, phone, address)
  VALUES (
    NEW.id,
    v_org_id,
    COALESCE(v_name, ''),
    NEW.email,
    'admin',
    v_phone,
    v_address
  );

  RETURN NEW;
END;
$function$;

-- ---------------------------------------------------------------------------
-- Trigger: fire handle_new_user() on each new auth.users row. Guarded so it
-- only applies when the auth schema exists (real Supabase project) and the
-- trigger is not already present. Catalog lookups are name-based to avoid a
-- regclass cast error when auth.users is absent.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'auth' AND table_name = 'users') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger t
                       JOIN pg_class c ON c.oid = t.tgrelid
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE t.tgname = 'on_auth_user_created'
                         AND n.nspname = 'auth' AND c.relname = 'users') THEN
            CREATE TRIGGER on_auth_user_created
                AFTER INSERT ON auth.users
                FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
        END IF;
    END IF;
END $$;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('001_initial_schema')
ON CONFLICT (version) DO NOTHING;
