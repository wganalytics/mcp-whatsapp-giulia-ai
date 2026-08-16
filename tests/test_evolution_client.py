"""Testes do cliente Evolution — sem rede.

O caso que originou este módulo é `test_cliente_e_reaproveitado`: cada chamada de tool
criava um `httpx.Client` novo que nunca era fechado. Num servidor MCP de vida longa,
isso vaza um pool de conexões por chamada.

O transporte HTTP é substituído por `httpx.MockTransport`, então nada sai da máquina.
"""
import sys
from pathlib import Path

import httpx
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import evolution_client  # noqa: E402
from evolution_client import (  # noqa: E402
    EvolutionClient,
    EvolutionConfigError,
    _extract_text,
    close_client,
    get_client,
)
from group_controller import GroupController  # noqa: E402
from send_giulia_ai import SendGiuliaAI  # noqa: E402


ENV = {
    "EVOLUTION_BASE_URL": "http://evolution.test:8080",
    "EVOLUTION_API_KEY": "chave-de-teste",
    "EVOLUTION_INSTANCE": "instancia-teste",
}


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    """Isola cada teste: env previsível e cliente compartilhado zerado."""
    for chave, valor in ENV.items():
        monkeypatch.setenv(chave, valor)
    close_client()
    yield
    close_client()


class FakeAPI:
    """Dublê do transporte HTTP: registra as requisições e devolve respostas fixas."""

    def __init__(self, respostas=None):
        self.requisicoes = []
        self.respostas = respostas or {}

    def transport(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requisicoes.append(request)
            corpo = self.respostas.get(request.url.path, {})
            return httpx.Response(200, json=corpo)
        return httpx.MockTransport(handler)

    def cliente(self):
        c = EvolutionClient()
        c._client = httpx.Client(
            base_url=ENV["EVOLUTION_BASE_URL"],
            headers={"apikey": ENV["EVOLUTION_API_KEY"]},
            transport=self.transport(),
        )
        return c


# --------------------------------------------------------------------------
# O vazamento que motivou a correção
# --------------------------------------------------------------------------

def test_cliente_e_reaproveitado():
    """Duas chamadas a get_client() devolvem a MESMA instância — sem pool novo."""
    assert get_client() is get_client()


def test_controllers_compartilham_o_mesmo_cliente():
    """Antes, cada GroupController()/SendGiuliaAI() abria um httpx.Client próprio."""
    assert GroupController().client is SendGiuliaAI().client


def test_close_client_libera_o_pool():
    cliente = get_client()
    close_client()
    assert cliente._client.is_closed


def test_close_client_permite_recriar():
    primeiro = get_client()
    close_client()
    assert get_client() is not primeiro


def test_close_e_idempotente():
    cliente = get_client()
    cliente.close()
    cliente.close()  # não pode levantar
    assert cliente._client.is_closed


def test_context_manager_fecha():
    with EvolutionClient() as c:
        assert not c._client.is_closed
    assert c._client.is_closed


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

@pytest.mark.parametrize("faltando", list(ENV))
def test_configuracao_incompleta_falha_claro(monkeypatch, faltando):
    monkeypatch.delenv(faltando)
    with pytest.raises(EvolutionConfigError):
        EvolutionClient()


def test_erro_de_configuracao_nao_deixa_cliente_quebrado(monkeypatch):
    """Uma criação que falha não pode ficar cacheada como cliente compartilhado."""
    monkeypatch.delenv("EVOLUTION_API_KEY")
    with pytest.raises(EvolutionConfigError):
        get_client()
    assert evolution_client._shared_client is None


def test_barra_final_da_base_url_e_removida(monkeypatch):
    monkeypatch.setenv("EVOLUTION_BASE_URL", "http://evolution.test:8080/")
    assert EvolutionClient().base_url == "http://evolution.test:8080"


# --------------------------------------------------------------------------
# Chamadas à API
# --------------------------------------------------------------------------

def test_fetch_all_groups_envia_apikey_no_header():
    api = FakeAPI({"/group/fetchAllGroups/instancia-teste": []})
    api.cliente().fetch_all_groups()
    assert api.requisicoes[0].headers["apikey"] == "chave-de-teste"


@pytest.mark.parametrize("corpo,esperado", [
    ({"/group/fetchAllGroups/instancia-teste": [{"id": "1@g.us", "subject": "Time"}]}, 1),
    ({"/group/fetchAllGroups/instancia-teste": {"groups": [{"id": "1@g.us"}]}}, 1),
])
def test_fetch_all_groups_normaliza_formatos(corpo, esperado):
    assert len(api_com(corpo).fetch_all_groups()) == esperado


@pytest.mark.parametrize("corpo", [
    {"/chat/findMessages/instancia-teste": [{"messageTimestamp": 1}]},
    {"/chat/findMessages/instancia-teste": {"messages": [{"messageTimestamp": 1}]}},
    {"/chat/findMessages/instancia-teste": {"messages": {"records": [{"messageTimestamp": 1}]}}},
])
def test_find_messages_normaliza_formatos(corpo):
    assert len(api_com(corpo).find_messages("1@g.us")) == 1


def api_com(corpo):
    return FakeAPI(corpo).cliente()


def test_send_text_monta_o_payload():
    api = FakeAPI({"/message/sendText/instancia-teste": {"key": {"id": "abc"}}})
    api.cliente().send_text("5511999999999", "oi")
    import json
    payload = json.loads(api.requisicoes[0].content)
    assert payload == {"number": "5511999999999", "text": "oi"}


# --------------------------------------------------------------------------
# Extração de texto e filtro por data
# --------------------------------------------------------------------------

@pytest.mark.parametrize("obj,esperado", [
    ({"conversation": "oi"}, "oi"),
    ({"extendedTextMessage": {"text": "resposta"}}, "resposta"),
    ({"imageMessage": {"caption": "foto"}}, "foto"),
    ({"videoMessage": {"caption": "video"}}, "video"),
    ({"documentMessage": {"caption": "doc"}}, "doc"),
    ({"audioMessage": {}}, ""),
    (None, ""),
    ({}, ""),
])
def test_extract_text(obj, esperado):
    assert _extract_text(obj) == esperado


class ClienteFake:
    def __init__(self, mensagens):
        self._mensagens = mensagens

    def find_messages(self, group_id):
        return self._mensagens


def test_filtro_por_data_recorta_o_intervalo():
    from datetime import datetime
    ts = lambda s: int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp())
    mensagens = [
        {"messageTimestamp": ts("2026-07-01 10:00:00"), "message": {"conversation": "antes"}},
        {"messageTimestamp": ts("2026-07-15 10:00:00"), "message": {"conversation": "dentro"}},
        {"messageTimestamp": ts("2026-07-30 10:00:00"), "message": {"conversation": "depois"}},
    ]
    controller = GroupController(client=ClienteFake(mensagens))
    resultado = controller.get_messages(
        "1@g.us", "2026-07-10 00:00:00", "2026-07-20 00:00:00"
    )
    assert [m.get_text() for m in resultado] == ["dentro"]


# --------------------------------------------------------------------------
# Normalização do destino
# --------------------------------------------------------------------------

from send_giulia_ai import normalizar_destino  # noqa: E402


@pytest.mark.parametrize("entrada,esperado", [
    ("27999998888", "5527999998888"),        # DDD + 9 dígitos
    ("2733334444", "552733334444"),          # DDD + 8 dígitos
    ("(27) 99999-8888", "5527999998888"),    # com máscara
    ("5527999998888", "5527999998888"),      # já tem o 55
])
def test_numero_ganha_codigo_do_pais(entrada, esperado):
    """Antes, o '55' só existia como instrução no docstring — dependia do LLM."""
    assert normalizar_destino(entrada) == esperado


@pytest.mark.parametrize("jid", [
    "120363000000000000@g.us",
    "5527999997777@s.whatsapp.net",
])
def test_jid_passa_intacto(jid):
    assert normalizar_destino(jid) == jid


def test_send_text_recebe_o_numero_normalizado():
    api = FakeAPI({"/message/sendText/instancia-teste": {"key": {"id": "abc"}}})
    SendGiuliaAI(client=api.cliente()).textMessage("27999998888", "oi")
    import json
    assert json.loads(api.requisicoes[0].content)["number"] == "5527999998888"


def test_textmessage_devolve_a_resposta_da_evolution():
    """A tool precisa do id da mensagem; antes o retorno era descartado."""
    api = FakeAPI({"/message/sendText/instancia-teste": {"key": {"id": "MSG123"}}})
    resposta = SendGiuliaAI(client=api.cliente()).textMessage("5527999998888", "oi")
    assert resposta["key"]["id"] == "MSG123"
