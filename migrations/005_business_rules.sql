-- =============================================================================
-- 005_business_rules.sql
--
-- Las reglas del negocio como dato: cuándo atiende cada taller, cuántos carros
-- puede recibir y cuánto dura cada servicio.
--
-- Hoy nada de esto existe. El horario de Toyopana está QUEMADO en el nodo
-- `menu_horarios` de services/inbound_service.py, y no hay noción alguna de
-- capacidad ni de duración. Sin estas tablas el bot no tiene contra qué validar
-- una solicitud de cita, y la agenda web no puede saber qué bloque mostrar
-- libre.
--
-- Tres tablas:
--
--   business_hours     La semana típica. Una fila por día.
--   business_calendar  Excepciones por fecha (feriados, cierres, horario
--                      especial). Pisa a business_hours.
--   service_types      Catálogo de servicios con su duración.
--
-- Resolución de un día, en orden estricto:
--   1. ¿Hay fila en business_calendar para esa fecha? -> esa manda
--   2. ¿No? -> business_hours para ese día de la semana
--   3. ¿Tampoco? -> CERRADO
--
-- El paso 3 es deliberado: sin configuración, cerrado. Una organización recién
-- creada no debe empezar a aceptar citas a cualquier hora.
--
-- Idempotente, al estilo de 001/002/003/004: PK y CHECK inline, FKs en bloque
-- DO guardado, RLS activa con cero políticas (deny total; el backend entra con
-- service_role), y auto-registro en schema_migrations.
--
-- Spec: docs/superpowers/specs/2026-09-03-reglas-del-negocio-design.md
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Horario semanal: la plantilla
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_hours (
    organization_id      uuid     NOT NULL,
    -- 0=domingo … 6=sábado, igual que extract(dow), para que la consulta sea
    -- una comparación directa y no una tabla de traducción.
    weekday              smallint NOT NULL,
    is_open              boolean  NOT NULL DEFAULT true,
    opens_at             time,
    closes_at            time,
    -- Tope del día. NULL = sin tope.
    max_citas            smallint,
    -- Cuántos carros caben a la MISMA hora. Con la agenda visible no basta un
    -- tope diario: hay que saber qué bloque de una hora mostrar ocupado.
    -- Default 1 = un carro por hora. Dos bahías -> 2.
    capacidad_simultanea smallint NOT NULL DEFAULT 1,
    CONSTRAINT business_hours_pkey PRIMARY KEY (organization_id, weekday),
    CONSTRAINT business_hours_weekday_check CHECK (weekday BETWEEN 0 AND 6),
    -- Un día abierto sin horas es una trampa: el bot no sabría qué validar y
    -- dejaría pasar cualquier hora.
    CONSTRAINT business_hours_open_needs_times CHECK (
        NOT is_open OR (opens_at IS NOT NULL AND closes_at IS NOT NULL AND opens_at < closes_at)
    ),
    CONSTRAINT business_hours_max_citas_check CHECK (max_citas IS NULL OR max_citas > 0),
    CONSTRAINT business_hours_capacidad_check CHECK (capacidad_simultanea > 0)
);

-- ---------------------------------------------------------------------------
-- 2. Excepciones por fecha: feriados, cierres, horario especial
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_calendar (
    organization_id      uuid     NOT NULL,
    date                 date     NOT NULL,
    -- Default false: la razón habitual de crear una fila aquí es cerrar.
    is_open              boolean  NOT NULL DEFAULT false,
    opens_at             time,
    closes_at            time,
    max_citas            smallint,
    -- NULL = hereda la de business_hours; un número la pisa (media jornada con
    -- un solo mecánico, por ejemplo).
    capacidad_simultanea smallint,
    reason               text,
    CONSTRAINT business_calendar_pkey PRIMARY KEY (organization_id, date),
    CONSTRAINT business_calendar_open_needs_times CHECK (
        NOT is_open OR (opens_at IS NOT NULL AND closes_at IS NOT NULL AND opens_at < closes_at)
    ),
    CONSTRAINT business_calendar_max_citas_check CHECK (max_citas IS NULL OR max_citas > 0),
    CONSTRAINT business_calendar_capacidad_check CHECK (
        capacidad_simultanea IS NULL OR capacidad_simultanea > 0
    )
);

-- ---------------------------------------------------------------------------
-- 3. Catálogo de servicios con su duración
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_types (
    id               uuid     NOT NULL DEFAULT gen_random_uuid(),
    organization_id  uuid     NOT NULL,
    name             text     NOT NULL,
    -- Piso de 60 min: una cita dura mínimo una hora. Es regla del negocio, no
    -- del software; relajarla el día que exista un servicio de media hora es
    -- una línea de migración.
    duration_minutes smallint NOT NULL DEFAULT 60,
    active           boolean  NOT NULL DEFAULT true,
    sort_order       smallint NOT NULL DEFAULT 0,
    CONSTRAINT service_types_pkey PRIMARY KEY (id),
    CONSTRAINT service_types_org_name_unique UNIQUE (organization_id, name),
    CONSTRAINT service_types_duration_check CHECK (duration_minutes >= 60)
);

-- Enlace aditivo: convive con citas.service_type (texto libre) sin romperlo.
ALTER TABLE citas ADD COLUMN IF NOT EXISTS service_type_id uuid;

-- ===========================================================================
-- FOREIGN KEYS (bloque guardado, patrón de 001)
-- ===========================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'business_hours_organization_id_fkey'
                     AND conrelid = 'public.business_hours'::regclass) THEN
        ALTER TABLE business_hours ADD CONSTRAINT business_hours_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'business_calendar_organization_id_fkey'
                     AND conrelid = 'public.business_calendar'::regclass) THEN
        ALTER TABLE business_calendar ADD CONSTRAINT business_calendar_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'service_types_organization_id_fkey'
                     AND conrelid = 'public.service_types'::regclass) THEN
        ALTER TABLE service_types ADD CONSTRAINT service_types_organization_id_fkey
            FOREIGN KEY (organization_id) REFERENCES organization(id) ON DELETE CASCADE;
    END IF;

    -- ON DELETE SET NULL, no CASCADE: borrar un tipo de servicio no puede
    -- borrar las citas que lo usaron.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'citas_service_type_id_fkey'
                     AND conrelid = 'public.citas'::regclass) THEN
        ALTER TABLE citas ADD CONSTRAINT citas_service_type_id_fkey
            FOREIGN KEY (service_type_id) REFERENCES service_types(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_service_types_org_active
    ON service_types USING btree (organization_id, active);

-- ===========================================================================
-- ROW LEVEL SECURITY: activa, sin políticas => deny total para anon/authenticated
-- ===========================================================================
ALTER TABLE business_hours    ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_calendar ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_types     ENABLE ROW LEVEL SECURITY;

-- ===========================================================================
-- DATOS INICIALES: el horario real de Suspensiones Toyopana
--
-- Se busca por slug en vez de incrustar un UUID, para que la migración sea
-- reproducible en cualquier ambiente.
--
-- max_citas y capacidad_simultanea quedan como vienen (NULL y 1): son las dos
-- preguntas pendientes para el taller — "¿cuántos carros al día?" y "¿cuántos
-- a la misma hora?" — y un número inventado hace que el bot rechace citas que
-- sí podían tomar.
-- ===========================================================================
INSERT INTO business_hours (organization_id, weekday, is_open, opens_at, closes_at)
SELECT o.id, v.weekday, v.is_open, v.opens_at, v.closes_at
FROM organization o
CROSS JOIN (VALUES
    (0::smallint, false, NULL::time,       NULL::time),        -- domingo
    (1::smallint, true,  '08:00'::time,    '17:00'::time),     -- lunes
    (2::smallint, true,  '08:00'::time,    '17:00'::time),     -- martes
    (3::smallint, true,  '08:00'::time,    '17:00'::time),     -- miércoles
    (4::smallint, true,  '08:00'::time,    '17:00'::time),     -- jueves
    (5::smallint, true,  '08:00'::time,    '17:00'::time),     -- viernes
    (6::smallint, true,  '08:00'::time,    '15:00'::time)      -- sábado
) AS v(weekday, is_open, opens_at, closes_at)
WHERE o.slug = 'toyopana'
ON CONFLICT (organization_id, weekday) DO NOTHING;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('005_business_rules')
ON CONFLICT (version) DO NOTHING;
