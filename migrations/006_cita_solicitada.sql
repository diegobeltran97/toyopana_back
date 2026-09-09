-- =============================================================================
-- 006_cita_solicitada.sql
--
-- El estado con el que nace una cita pedida por el cliente: `solicitada`.
--
-- Hoy el ciclo empieza en `agendada`, que significa "el taller la puso en el
-- calendario". Falta el paso previo: "el cliente la pidió, nadie la ha mirado".
-- Sin él, una cita creada desde la agenda web nacería FIRME, y el cliente se
-- iría creyendo que el taller lo espera.
--
--   solicitada ──> agendada ──> confirmada ──> cumplida
--        │              │             │      └─> no_show
--        └─> cancelada  └─> cancelada └─> cancelada
--
-- `solicitada` solo transiciona a `agendada` o `cancelada`: una cita que nadie
-- aceptó no puede haberse cumplido.
--
-- EL DEFAULT DE LA COLUMNA NO CAMBIA. Sigue siendo 'agendada' para que el modal
-- que ya usa el taller siga creando citas reales; el bot pasa 'solicitada'
-- explícitamente. Cambiarlo convertiría en solicitudes las citas que el taller
-- crea a mano.
--
-- Seguro de aplicar: producción tiene 1 sola cita, en 'cancelada', así que el
-- DROP/ADD del CHECK revalida una fila.
--
-- Idempotente, al estilo de 001-005. Aditiva: va directo a producción según la
-- política del proyecto.
--
-- Spec: docs/superpowers/specs/2026-09-03-solicitud-de-cita-por-whatsapp-design.md
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. El estado nuevo
-- ---------------------------------------------------------------------------
ALTER TABLE citas DROP CONSTRAINT IF EXISTS citas_status_check;
ALTER TABLE citas ADD CONSTRAINT citas_status_check CHECK ((status = ANY (ARRAY[
    'solicitada'::text,
    'agendada'::text,
    'confirmada'::text,
    'cumplida'::text,
    'no_show'::text,
    'cancelada'::text
])));

-- ---------------------------------------------------------------------------
-- 2. De dónde vino la cita
--
-- Se conserva después de aceptarla, cuando el estado ya no lo dice: es cómo se
-- demuestra cuántas citas produjo el bot, que es justo lo que el cliente está
-- pagando. NULL = origen desconocido (las creadas antes de esta migración), no
-- 'app'.
-- ---------------------------------------------------------------------------
ALTER TABLE citas ADD COLUMN IF NOT EXISTS created_via text;
ALTER TABLE citas DROP CONSTRAINT IF EXISTS citas_created_via_check;
ALTER TABLE citas ADD CONSTRAINT citas_created_via_check
    CHECK (created_via IS NULL OR created_via = ANY (ARRAY['app'::text, 'bot'::text]));

-- ---------------------------------------------------------------------------
-- 3. Lo que el cliente pidió, en sus palabras
--
-- Antes de que nadie lo interprete. Sirve cuando la fecha propuesta no encaja y
-- hay que entender qué quería realmente.
-- ---------------------------------------------------------------------------
ALTER TABLE citas ADD COLUMN IF NOT EXISTS solicitud_texto text;

-- ---------------------------------------------------------------------------
-- 4. Índice para la bandeja de solicitudes pendientes
--
-- El taller entra al calendario a ver "qué me pidieron". Sin índice, esa
-- consulta recorre la tabla entera cada vez.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_citas_org_solicitadas
    ON citas USING btree (organization_id, scheduled_at)
    WHERE status = 'solicitada';

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('006_cita_solicitada')
ON CONFLICT (version) DO NOTHING;
