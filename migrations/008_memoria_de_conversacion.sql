-- =============================================================================
-- 008_memoria_de_conversacion.sql
--
-- La conversación recuerda en qué nodo va.
--
-- El bot decidía SOLO con el mensaje que tenía enfrente. Un texto libre que no
-- pegaba con ninguna palabra clave caía al menú de bienvenida -- y la
-- respuesta a la pregunta del propio bot es exactamente eso. Capturado en
-- producción el 2026-09-24:
--
--     bot      Hola 👋 ¿En qué te podemos ayudar?   [Ver opciones]
--     cliente  (toca "Cotización")
--     bot      Para cotizarte necesitamos la pieza, marca, modelo y año
--     cliente  Jetour Dashing año 2025 los amortiguadores
--     bot      Hola 👋 ¿En qué te podemos ayudar?   [Ver opciones]   <-- el bug
--
-- Visto desde el cliente, el bot pregunta, le contestan, y vuelve a empezar.
--
-- Dos columnas, las dos aditivas:
--
--   bot_node     el último nodo que mandó el bot. NULL = nadie ha hablado, y
--                es el default, así que toda fila existente queda como un chat
--                frío: el saludo les sigue funcionando igual que hoy.
--
--   bot_node_at  cuándo se tocó ese estado por última vez. Es el reloj de la
--                ventana de sesión (24h), y lo que mide es el SILENCIO DEL
--                CLIENTE, no el del bot: el taller contesta desde su propio
--                WhatsApp y esos mensajes no nos llegan (el parser descarta
--                from_me). Medirlo desde el bot haría aparecer el menú en
--                medio de una conversación que una persona está atendiendo.
--
-- No hay backfill y no hace falta: NULL es el estado correcto para todo lo que
-- ya existe. Un chat vivo pierde a lo sumo su memoria una vez, y lo peor que
-- le pasa es recibir el menú un mensaje de más.
--
-- Idempotente, al estilo de 001-007. Aditiva: va directo a producción.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. En qué nodo va la conversación
-- ---------------------------------------------------------------------------
ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS bot_node    text;
ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS bot_node_at timestamptz;

-- Las dos van juntas o no van: un nodo sin marca de tiempo no se puede vencer
-- y dejaría la conversación con el bot callado para siempre; una marca sin
-- nodo no dice nada. El código las escribe siempre a la vez (tocar_estado_bot).
ALTER TABLE wa_conversations DROP CONSTRAINT IF EXISTS wa_conversations_bot_node_check;
ALTER TABLE wa_conversations ADD CONSTRAINT wa_conversations_bot_node_check CHECK (
    bot_node IS NULL OR bot_node_at IS NOT NULL
);

-- ===========================================================================
-- Record this migration
-- ===========================================================================
INSERT INTO schema_migrations (version) VALUES ('008_memoria_de_conversacion')
ON CONFLICT (version) DO NOTHING;
