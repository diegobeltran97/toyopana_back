"""Tests for services/inbound_service.py -- the post-200 half of the webhook.

Everything here runs AFTER the provider already got its 200, so the governing
rule is: nothing may raise. A failure is logged and recorded, never propagated,
because there is no longer a status code to put it in.

Repositories and the provider are replaced with hand-written doubles.
"""

from datetime import datetime, timezone

import pytest

import services.inbound_service as inbound_service
from core.result import Result
from schemas.inbound import InboundMessage
from schemas.messaging import SentMessage

ORG = "11111111-1111-1111-1111-111111111111"
CONVERSATION_ID = "22222222-2222-2222-2222-222222222222"


def _event_from(phone):
    """Same event, from a given sender."""
    e = _event()
    return e.model_copy(update={"from_phone": phone})


def _event(body="Hola", reply_id=None):
    return InboundMessage(
        provider="whapi",
        provider_event_id="wamid.1",
        chat_id="50768510658@s.whatsapp.net",
        from_phone="+50768510658",
        from_name="Juan Pérez",
        body=body,
        reply_id=reply_id,
        received_at=datetime(2026, 8, 28, 14, 20, tzinfo=timezone.utc),
    )


async def entregar(provider, event, org=ORG):
    """handle_inbound, then wait out the debounce.

    Replies are no longer immediate: a burst is answered once, after the
    customer stops writing. Tests that assert on the reply have to wait for
    that, the same as a real customer does.
    """
    await inbound_service.handle_inbound(provider, organization_id=org, event=event)
    await inbound_service.wait_for_pending()


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Ningún test de este módulo sale a la red.

    El nodo de horarios lee business_hours desde Supabase, y `app/.env` apunta
    a PRODUCCIÓN: sin este stub cada test hace una consulta real. Las clases que
    prueban el horario sustituyen esto con su propio valor.
    """
    async def horario_de_prueba(_org):
        return "Lunes a viernes: 8:00 a.m. – 5:00 p.m.\nSábados: 8:00 a.m. – 3:00 p.m."

    monkeypatch.setattr(inbound_service, "leer_texto_de_horario", horario_de_prueba)


@pytest.fixture(autouse=True)
def _debounce_corto(monkeypatch):
    """Keep the suite fast, and never leave a timer running between tests."""
    monkeypatch.setattr(inbound_service, "DEBOUNCE_SECONDS", 0.05)
    inbound_service._reset_debounce()
    yield
    inbound_service._reset_debounce()


class FakeProvider:
    """Records what was sent; satisfies only what the service calls."""

    def __init__(self, result=None):
        self.result = result or Result.success(SentMessage(id="out1", to="x", status="sent"))
        self.sent = []        # interactive messages
        self.sent_text = []   # plain text messages

    async def send_interactive(self, msg):
        self.sent.append(msg)
        return self.result

    async def send_text(self, msg):
        self.sent_text.append(msg)
        return self.result


@pytest.fixture
def repo(monkeypatch):
    """A stand-in for the conversation/customer persistence."""

    class Repo:
        def __init__(self):
            self.status = "bot"
            self.messages = []
            self.window_touched = False

        async def upsert_conversation(self, **kwargs):
            # One conversation per chat, like the real UNIQUE
            # (organization_id, wa_chat_id). Returning a single id for every
            # chat would have two customers share one debounce buffer.
            chat = kwargs.get("chat_id", "")
            return {
                "id": CONVERSATION_ID if "50768510658" in chat else f"conv-{chat}",
                "status": self.status,
            }

        async def record_message(self, **kwargs):
            self.messages.append(kwargs)

        async def touch_last_inbound(self, **kwargs):
            self.window_touched = True

    r = Repo()
    monkeypatch.setattr(inbound_service, "upsert_conversation", r.upsert_conversation)
    monkeypatch.setattr(inbound_service, "record_message", r.record_message)
    monkeypatch.setattr(inbound_service, "touch_last_inbound", r.touch_last_inbound)
    return r


class TestPersistence:
    async def test_stores_the_inbound_message(self, repo):
        await entregar(FakeProvider(), _event())

        inbound = [m for m in repo.messages if m["direction"] == "inbound"]
        assert len(inbound) == 1

    async def test_the_stored_message_keeps_the_provider_id_for_deduplication(self, repo):
        await entregar(FakeProvider(), _event())

        inbound = [m for m in repo.messages if m["direction"] == "inbound"][0]
        assert inbound["wa_message_id"] == "wamid.1"

    async def test_refreshes_the_24h_window(self, repo):
        await entregar(FakeProvider(), _event())

        assert repo.window_touched is True


class TestWelcomeReply:
    async def test_replies_with_the_welcome_menu(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event())

        assert len(provider.sent) == 1

    async def test_the_menu_offers_the_four_business_options(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event())

        assert [b.id for b in provider.sent[0].buttons] == [
            "menu_agendar_cita",
            "menu_cotizacion",
            "menu_horarios",
            "menu_otro",
        ]

    async def test_the_menu_goes_back_to_whoever_wrote_in(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event())

        assert provider.sent[0].phone == "+50768510658"

    async def test_the_sent_menu_is_recorded_as_an_outbound_message(self, repo):
        """Otherwise the thread has a gap and the marketing metrics undercount."""
        await entregar(FakeProvider(), _event())

        assert [m for m in repo.messages if m["direction"] == "outbound"]


class TestHumanHandoff:
    async def test_does_not_reply_when_an_agent_owns_the_conversation(self, repo):
        """wa_conversations.status leaves 'bot' when a human takes over. Replying
        anyway would have the bot talk over its own colleague."""
        repo.status = "agent"
        provider = FakeProvider()

        await entregar(provider, _event())

        assert provider.sent == []

    async def test_still_stores_the_message_when_a_human_owns_it(self, repo):
        repo.status = "agent"

        await entregar(FakeProvider(), _event())

        assert [m for m in repo.messages if m["direction"] == "inbound"]


class TestFailuresAreContained:
    async def test_a_provider_failure_does_not_raise(self, repo):
        """We already answered 200. Raising here would only crash a background
        task and lose the message we just stored."""
        provider = FakeProvider(Result.failure("rate_limit", status_code=429))

        await entregar(provider, _event())

    async def test_a_failed_send_is_not_recorded_as_an_outbound_message(self, repo):
        provider = FakeProvider(Result.failure("rate_limit", status_code=429))

        await entregar(provider, _event())

        assert [m for m in repo.messages if m["direction"] == "outbound"] == []


class TestAllowlistDeTesting:
    """Test-mode allowlist: while testing against a live channel, only the
    numbers listed may receive a reply.

    Deliberately gated at the REPLY step, not at the webhook: an unlisted
    message is still stored, so testing does not cost visibility into what real
    customers are sending. Empty setting = disabled = everyone gets a reply,
    so forgetting to set it can never silence the bot.
    """

    @pytest.fixture
    def allowlist(self, monkeypatch):
        def _set(value):
            monkeypatch.setattr(
                inbound_service.settings, "WHATSAPP_ALLOWED_NUMBERS", value, raising=False
            )
        return _set

    async def test_a_listed_number_gets_the_welcome_menu(self, repo, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await entregar(provider, _event_from("+50768510658")
        )

        assert len(provider.sent) == 1

    async def test_an_unlisted_number_gets_no_reply(self, repo, allowlist):
        allowlist("50768510658")
        provider = FakeProvider()

        await entregar(provider, _event_from("+50761112222")
        )

        assert provider.sent == []

    async def test_an_unlisted_number_is_still_stored(self, repo, allowlist):
        """Testing must not blind us to what real customers are writing."""
        allowlist("50768510658")

        await entregar(FakeProvider(), _event_from("+50761112222")
        )

        assert [m for m in repo.messages if m["direction"] == "inbound"]

    async def test_an_empty_setting_disables_the_allowlist(self, repo, allowlist):
        """The default. Forgetting to configure it must never silence the bot."""
        allowlist("")
        provider = FakeProvider()

        await entregar(provider, _event_from("+50761112222")
        )

        assert len(provider.sent) == 1

    async def test_the_number_matches_however_it_is_written(self, repo, allowlist):
        """A leading + or spaces in the env var must not silently stop replies."""
        allowlist("+507 6851-0658")
        provider = FakeProvider()

        await entregar(provider, _event_from("+50768510658")
        )

        assert len(provider.sent) == 1

    async def test_several_numbers_can_be_listed(self, repo, allowlist):
        allowlist("50768510658, 50761112222")
        provider = FakeProvider()

        await entregar(provider, _event_from("+50761112222")
        )

        assert len(provider.sent) == 1


class TestFlujoDeBotones:
    """The reply tree: a tapped button routes to its node, deterministically.

    This is the half of the bot that costs nothing per message. Anything the
    tree does not cover falls through to the welcome menu today, and to the
    LLM later -- the fallback is the seam, not a dead end.
    """

    async def test_horarios_devuelve_el_horario_y_no_el_menu(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios")
        )

        [enviado] = provider.sent_text
        assert "orario" in enviado.body

    async def test_horarios_incluye_la_direccion_del_taller(self, repo):
        """Asserts the address itself, not the heading above it. An earlier
        version checked for the word "ubicación" and broke when the heading was
        reworded -- while the message was still perfectly correct."""
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios")
        )

        [enviado] = provider.sent_text
        assert "Plaza Toledo" in enviado.body

    async def test_una_respuesta_de_solo_texto_no_manda_botones(self, repo):
        """A node with no options must go out via send_text: send_interactive
        requires at least one button and would reject it."""
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios")
        )

        assert provider.sent == []

    async def test_el_menu_de_bienvenida_ofrece_horarios(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event())

        assert "menu_horarios" in [b.id for b in provider.sent[0].buttons]

    async def test_texto_libre_sigue_devolviendo_la_bienvenida(self, repo):
        """Until the LLM lands, anything off-tree gets the menu again."""
        provider = FakeProvider()

        await entregar(provider, _event(body="necesito unas pastillas")
        )

        assert len(provider.sent) == 1

    async def test_un_boton_desconocido_no_rompe_nada(self, repo):
        """A stale menu in an old chat can send an id the tree no longer has."""
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="boton_que_ya_no_existe")
        )

        assert len(provider.sent) == 1

    async def test_la_respuesta_de_texto_queda_registrada(self, repo):
        await entregar(FakeProvider(), _event(reply_id="menu_horarios")
        )

        assert [m for m in repo.messages if m["direction"] == "outbound"]


class TestPalabrasClaveEnTextoLibre:
    """Free text that clearly names a menu option routes to it directly.

    Cheap and worth it: someone who types "cual es el horario" wants the
    answer, not a menu asking them to pick it. Each keyword hit is also one
    fewer LLM call once the model lands, so this layer keeps paying for itself.

    Deliberately narrow -- only unambiguous words. Guessing wrong is worse
    than showing the menu, because the customer gets a confident answer to a
    question they did not ask.
    """

    async def _responder(self, texto, repo):
        provider = FakeProvider()
        await entregar(provider, _event(body=texto)
        )
        return provider

    async def test_horario_devuelve_el_horario(self, repo):
        provider = await self._responder("cual es el horario?", repo)

        assert provider.sent_text and "Plaza Toledo" in provider.sent_text[0].body

    async def test_ubicacion_devuelve_la_direccion(self, repo):
        provider = await self._responder("me pasas la ubicacion", repo)

        assert provider.sent_text and "Plaza Toledo" in provider.sent_text[0].body

    async def test_funciona_con_tilde(self, repo):
        """"ubicación" and "ubicacion" must behave the same -- people type both."""
        provider = await self._responder("cuál es la ubicación?", repo)

        assert provider.sent_text

    async def test_funciona_en_mayusculas(self, repo):
        provider = await self._responder("HORARIO", repo)

        assert provider.sent_text

    async def test_donde_quedan_devuelve_la_direccion(self, repo):
        provider = await self._responder("donde quedan ubicados", repo)

        assert provider.sent_text

    async def test_texto_sin_palabra_clave_sigue_devolviendo_el_menu(self, repo):
        provider = await self._responder("necesito pastillas para un Corolla", repo)

        assert provider.sent and not provider.sent_text


class TestDebounce:
    """Wait for the customer to stop typing before answering.

    Measured on 4 days of the pilot's real traffic: 25% of inbound messages
    arrive within 25s of the previous one in the same chat. Answering each
    fragment means replying before the customer finished the thought --
    "Buenas" / "venden cubre carter?" / "Elantra 2011" is ONE question sent as
    three messages, and today it draws three welcome menus.
    """

    @pytest.fixture(autouse=True)
    def sin_espera(self, monkeypatch):
        """A tiny delay, not zero: these assert the aggregation, not the
        clock, but zero would let a timer fire between two handle_inbound
        calls and make the tests non-deterministic."""
        monkeypatch.setattr(inbound_service, "DEBOUNCE_SECONDS", 0.05)
        inbound_service._reset_debounce()

    async def _entra(self, provider, event):
        """Raw handle_inbound: these tests control the waiting themselves."""
        await inbound_service.handle_inbound(provider, organization_id=ORG, event=event)

    async def test_un_mensaje_suelto_recibe_una_respuesta(self, repo):
        provider = FakeProvider()

        await self._entra(provider, _event(body="Buenas"))
        await inbound_service.wait_for_pending()

        assert len(provider.sent) + len(provider.sent_text) == 1

    async def test_tres_mensajes_seguidos_reciben_UNA_respuesta(self, repo):
        """The regression this whole feature exists for."""
        provider = FakeProvider()

        await self._entra(provider, _event(body="Buenas"))
        await self._entra(provider, _event(body="venden cubre carter?"))
        await self._entra(provider, _event(body="Elantra 2011"))
        await inbound_service.wait_for_pending()

        assert len(provider.sent) + len(provider.sent_text) == 1

    async def test_la_decision_ve_todos_los_mensajes_de_la_rafaga(self, repo):
        """Deciding on the last message alone loses the question: someone who
        asks the schedule and then says "gracias" would be answered on
        "gracias"."""
        provider = FakeProvider()

        await self._entra(provider, _event(body="cual es el horario?"))
        await self._entra(provider, _event(body="gracias"))
        await inbound_service.wait_for_pending()

        assert provider.sent_text and "Plaza Toledo" in provider.sent_text[0].body

    async def test_los_tres_mensajes_igual_se_guardan(self, repo):
        """Debounce delays the REPLY, never the persistence."""
        provider = FakeProvider()

        await self._entra(provider, _event(body="Buenas"))
        await self._entra(provider, _event(body="venden cubre carter?"))
        await inbound_service.wait_for_pending()

        assert len([m for m in repo.messages if m["direction"] == "inbound"]) == 2

    async def test_un_tap_de_boton_responde_sin_esperar(self, repo):
        """A tap is a complete thought -- making the customer wait for it is
        latency with nothing bought."""
        provider = FakeProvider()

        await self._entra(provider, _event(reply_id="menu_horarios"))

        assert provider.sent_text  # already sent, before wait_for_pending()

    async def test_dos_conversaciones_no_se_cancelan_entre_si(self, repo):
        provider = FakeProvider()

        a = _event(body="hola")
        b = a.model_copy(update={"chat_id": "50761112222@s.whatsapp.net"})
        await self._entra(provider, a)
        await self._entra(provider, b)
        await inbound_service.wait_for_pending()

        assert len(provider.sent) + len(provider.sent_text) == 2


class TestTextoEnlatadoDeAnuncios:
    """WhatsApp prefills a canned message when someone taps an ad's button.
    It carries no information about what they want.

    Measured on the pilot's traffic: 78 of 669 inbound messages (12%) are this
    text. 70 arrive bare; in 8 the real question is appended to it. Of the bare
    ones, 29% are followed by the real question within 25 seconds.

    So it is NOT answered on sight -- that would reply before a third of
    customers said what they wanted. It is stripped as noise, and the decision
    is made on whatever is left. Nothing left means they only tapped the ad,
    and the menu is the right answer.
    """

    def test_el_texto_enlatado_solo_no_deja_nada(self):
        assert inbound_service._quitar_ruido("¡Hola! Quiero más información") == ""

    def test_la_otra_variante_tambien(self):
        texto = "¡Hola! Me gustaría conseguir más información sobre esto."

        assert inbound_service._quitar_ruido(texto) == ""

    def test_la_pregunta_pegada_al_enlatado_sobrevive(self):
        """Captured verbatim from production."""
        texto = "¡Hola! Quiero más información sobre cremallera para Nissan xtrail t30"

        assert inbound_service._quitar_ruido(texto) == "sobre cremallera para Nissan xtrail t30"

    def test_la_pregunta_en_otra_linea_sobrevive(self):
        texto = "¡Hola! Quiero más información\nTendrán amortiguadores para un mazda 3 2016"

        assert "amortiguadores" in inbound_service._quitar_ruido(texto)

    def test_un_mensaje_normal_no_se_toca(self):
        texto = "Cremallera para un hyundai elantra 2010 automatico"

        assert inbound_service._quitar_ruido(texto) == texto

    async def test_solo_el_enlatado_recibe_el_menu(self, repo):
        provider = FakeProvider()

        await entregar(provider, _event(body="¡Hola! Quiero más información"))

        assert len(provider.sent) == 1

    async def test_enlatado_mas_pregunta_decide_sobre_la_pregunta(self, repo):
        """The canned prefix must not drown the real question in the burst."""
        provider = FakeProvider()

        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event(body="¡Hola! Quiero más información")
        )
        await inbound_service.handle_inbound(
            provider, organization_id=ORG, event=_event(body="cual es el horario?")
        )
        await inbound_service.wait_for_pending()

        assert provider.sent_text and "Plaza Toledo" in provider.sent_text[0].body


class TestHorarioDesdeLaTabla:
    """El mensaje de horarios sale de business_hours, no de texto quemado.

    Cierra el riesgo de las dos fuentes: antes el horario estaba escrito a mano
    en este nodo Y en la tabla contra la que se validan las citas. El taller
    cambiaba su sábado en ajustes y el bot seguía diciendo la hora vieja.
    """

    @pytest.fixture
    def horario(self, monkeypatch):
        """Reemplaza la lectura de la tabla por un horario controlado."""
        def _set(texto):
            async def fake(_org):
                return texto
            monkeypatch.setattr(inbound_service, "leer_texto_de_horario", fake)
        return _set

    async def test_el_mensaje_usa_el_horario_de_la_tabla(self, repo, horario):
        horario("Lunes a viernes: 8:00 a.m. – 5:00 p.m.\nSábados: 8:00 a.m. – 1:00 p.m.")
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios"))

        assert "1:00 p.m." in provider.sent_text[0].body

    async def test_no_queda_horario_quemado_en_el_mensaje(self, repo, horario):
        """Si el texto fijo siguiera ahí, el mensaje traería las dos versiones."""
        horario("Lunes a viernes: 9:00 a.m. – 6:00 p.m.")
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios"))

        assert "5:00 p.m." not in provider.sent_text[0].body

    async def test_la_direccion_sigue_apareciendo(self, repo, horario):
        """El horario sale de la tabla; la dirección todavía no, y no debe
        perderse en el cambio."""
        horario("Lunes a viernes: 8:00 a.m. – 5:00 p.m.")
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios"))

        assert "Plaza Toledo" in provider.sent_text[0].body

    async def test_si_falla_la_lectura_el_bot_igual_responde(self, repo, monkeypatch):
        """Una caída de Supabase no puede dejar al cliente sin respuesta: el
        mensaje sale sin la sección de horario, con la dirección."""
        async def explota(_org):
            raise RuntimeError("supabase caída")
        monkeypatch.setattr(inbound_service, "leer_texto_de_horario", explota)
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_horarios"))

        assert provider.sent_text and "Plaza Toledo" in provider.sent_text[0].body


class TestElBotMandaElLinkDeAgenda:
    """Tocar "Agendar cita" manda el link, no un pedido de que escriba la fecha.

    Interpretar "el viernes temprano" en conversación era lo más frágil que
    íbamos a construir, y una conversación no puede mostrar lo que ya está
    ocupado. Por eso el bot no negocia la fecha: manda la agenda.
    """

    @pytest.fixture(autouse=True)
    def _secreto(self, monkeypatch):
        monkeypatch.setattr(inbound_service.settings, "AGENDA_TOKEN_SECRET",
                            "secreto-de-prueba", raising=False)
        monkeypatch.setattr(inbound_service.settings, "AGENDA_BASE_URL",
                            "https://toyopana.app", raising=False)

    async def _responder(self, repo):
        provider = FakeProvider()
        await entregar(provider, _event(reply_id="menu_agendar_cita"))
        return provider.sent_text[0].body

    async def test_manda_un_link(self, repo):
        assert "https://toyopana.app/agenda/" in await self._responder(repo)

    async def test_el_link_lleva_un_token_valido(self, repo):
        from services.agenda_token import leer_token

        cuerpo = await self._responder(repo)
        token = cuerpo.split("/agenda/")[1].split()[0].rstrip(".,")

        assert leer_token(token, secreto="secreto-de-prueba").organization_id == ORG

    async def test_dice_que_queda_pendiente_de_confirmacion(self, repo):
        """Lo único que impide que el cliente se vaya creyendo que ya tiene
        cita."""
        cuerpo = await self._responder(repo)

        assert "confirm" in cuerpo.lower()

    async def test_ya_no_le_pide_que_escriba_la_fecha(self, repo):
        """El texto viejo negociaba la fecha por chat."""
        cuerpo = await self._responder(repo)

        assert "qué día y hora te quedan bien" not in cuerpo

    async def test_sin_base_url_no_manda_un_link_roto(self, repo, monkeypatch):
        """Sin dominio el link sale como "/agenda/xxx": el cliente lo toca y no
        pasa nada. Mejor pedir los datos por chat que mandar algo roto."""
        monkeypatch.setattr(inbound_service.settings, "AGENDA_BASE_URL", "",
                            raising=False)
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_agendar_cita"))

        assert "/agenda/" not in provider.sent_text[0].body

    async def test_sin_secreto_configurado_el_bot_igual_responde(self, repo, monkeypatch):
        """Un .env incompleto no puede dejar al cliente sin respuesta: se cae al
        texto de siempre, que pide los datos por chat."""
        monkeypatch.setattr(inbound_service.settings, "AGENDA_TOKEN_SECRET", "",
                            raising=False)
        provider = FakeProvider()

        await entregar(provider, _event(reply_id="menu_agendar_cita"))

        assert provider.sent_text and len(provider.sent_text[0].body) > 20


class TestLaPalabraCitaTambienMandaElLink:
    """La página de link vencido promete: "escríbenos *cita* y te lo mandamos
    de una". El bot tiene que cumplirlo, y por la misma vía que el botón."""

    @pytest.fixture(autouse=True)
    def _secreto(self, monkeypatch):
        monkeypatch.setattr(inbound_service.settings, "AGENDA_TOKEN_SECRET",
                            "secreto-de-prueba", raising=False)
        monkeypatch.setattr(inbound_service.settings, "AGENDA_BASE_URL",
                            "https://toyopana.app", raising=False)

    @pytest.mark.parametrize("texto", [
        "cita",
        "Cita",
        "quiero una cita",
        "necesito agendar",
        "me pueden agendar para el viernes",
    ])
    async def test_manda_el_link(self, repo, texto):
        provider = FakeProvider()

        await entregar(provider, _event(body=texto))

        assert "/agenda/" in provider.sent_text[0].body

    async def test_no_confunde_palabras_que_la_contienen(self, repo):
        """"solicita", "necesitaba", "citroen" contienen "cita" o se le
        parecen; ninguna pide una cita."""
        provider = FakeProvider()

        await entregar(provider, _event(body="me solicitaron una cotización"))

        enviado = provider.sent_text + provider.sent
        assert "/agenda/" not in (getattr(enviado[0], "body", "") or "")
