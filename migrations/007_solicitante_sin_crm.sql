-- =============================================================================
-- 007_solicitante_sin_crm.sql
--
-- Una solicitud de cita ya no crea un cliente en el CRM.
--
-- El CRM es de la gente que de verdad lleva su carro al taller, cargada con el
-- formulario. Alguien que solo pidió una hora por la web todavía no es eso:
-- crearle ficha ensucia el directorio con personas que quizá nunca aparezcan, y
-- deja al taller sin poder distinguir a sus clientes de sus interesados.
--
-- Los datos del solicitante viven en la propia cita hasta que el taller decida
-- convertirlo en cliente:
--
--   solicitante_nombre     lo que escribió en la página
--   solicitante_telefono    por donde se le confirma
--
-- Y `customer_id` pasa a ser nullable, que es lo que hace posible una cita sin
-- ficha detrás. Ninguna fila existente lo tiene NULL, así que aflojar la
-- restricción no invalida nada.
--
-- Idempotente, al estilo de 001-006. Aditiva: va directo a producción.
--
-- Spec: docs/superpowers/specs/2026-09-03-solicitud-de-cita-por-whatsapp-design.md
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Una cita puede existir sin cliente en el CRM
-- ---------------------------------------------------------------------------
ALTER TABLE citas ALTER COLUMN customer_id DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Quién pidió la cita, mientras no sea todavía un cliente
--
-- El teléfono es el que importa: es por donde el taller le confirma, y sin él
-- una cita aceptada no le llega a nadie.
-- ---------------------------------------------------------------------------
ALTER TABLE citas ADD COLUMN IF NOT EXISTS solicitante_nombre   text;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS solicitante_telefono text;

-- Una cita tiene que saber a quién pertenece por alguna de las dos vías: una
-- ficha del CRM, o los datos que la persona dejó. Sin ninguna, es una cita
-- huérfana que nadie puede confirmar.
ALTER TABLE citas DROP CONSTRAINT IF EXISTS citas_tiene_a_quien_check;
ALTER TABLE citas ADD CONSTRAINT citas_tiene_a_quien_check CHECK (
    customer_id IS NOT NULL OR solicitante_telefono IS NOT NULL
);

-- ---------------------------------------------------------------------------
-- 3. Buscar una solicitud por teléfono
--
-- Para reconocer a alguien que vuelve a pedir cita, y para que el taller pueda
-- encontrarlo cuando aparezca con el carro.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_citas_solicitante_telefono
    ON citas USING btree (organization_id, solicitante_telefono)
    WHERE solicitante_telefono IS NOT NULL;

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('007_solicitante_sin_crm')
ON CONFLICT (version) DO NOTHING;
