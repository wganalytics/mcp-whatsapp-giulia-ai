"""Cliente HTTP real da Evolution API (gateway self-hosted de WhatsApp).

Toda configuração vem de variáveis de ambiente
(.env), nunca hardcoded. Alvo: Evolution API v2 (ajuste pontual de campos pode ser
necessário conforme a versão da sua instância).

O cliente é **compartilhado** entre as tools via :func:`get_client`. Antes, cada
chamada de tool instanciava um ``httpx.Client`` novo que nunca era fechado — num
servidor MCP de vida longa isso vaza um pool de conexões por chamada. Como o servidor
atende uma instância só, um cliente reaproveitado é o formato correto: mantém o
keep-alive e não acumula sockets.
"""
import atexit
import os
import threading
from typing import Any, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()


class EvolutionConfigError(RuntimeError):
    pass


def _extract_text(message_obj: Optional[dict]) -> str:
    """Extrai o texto de um objeto 'message' da Evolution, cobrindo os tipos comuns."""
    if not message_obj:
        return ""
    if "conversation" in message_obj:
        return message_obj["conversation"]
    if "extendedTextMessage" in message_obj:
        return message_obj["extendedTextMessage"].get("text", "")
    for media in ("imageMessage", "videoMessage", "documentMessage"):
        if media in message_obj:
            return message_obj[media].get("caption", "")
    return ""


class EvolutionClient:
    def __init__(self):
        self.base_url = (os.getenv("EVOLUTION_BASE_URL") or "").rstrip("/")
        self.api_key = os.getenv("EVOLUTION_API_KEY") or ""
        self.instance = os.getenv("EVOLUTION_INSTANCE") or ""
        if not (self.base_url and self.api_key and self.instance):
            raise EvolutionConfigError(
                "Configure EVOLUTION_BASE_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE no .env"
            )
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"apikey": self.api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )

    # ---- Grupos -------------------------------------------------------------
    def fetch_all_groups(self, get_participants: bool = False) -> list[dict]:
        resp = self._client.get(
            f"/group/fetchAllGroups/{self.instance}",
            params={"getParticipants": str(get_participants).lower()},
        )
        resp.raise_for_status()
        data = resp.json()
        # Evolution pode retornar lista direta ou {"groups": [...]}
        return data.get("groups", data) if isinstance(data, dict) else data

    # ---- Mensagens ----------------------------------------------------------
    def find_messages(self, remote_jid: str) -> list[dict]:
        resp = self._client.post(
            f"/chat/findMessages/{self.instance}",
            json={"where": {"key": {"remoteJid": remote_jid}}},
        )
        resp.raise_for_status()
        data = resp.json()
        # Normaliza os formatos conhecidos: lista | {"messages":{"records":[...]}} | {"messages":[...]}
        if isinstance(data, list):
            return data
        msgs = data.get("messages", data)
        if isinstance(msgs, dict):
            return msgs.get("records", [])
        return msgs or []

    # ---- Envio --------------------------------------------------------------
    def send_text(self, number: str, text: str, mentions: Optional[list[str]] = None) -> dict:
        payload: dict[str, Any] = {"number": number, "text": text}
        if mentions:
            payload["mentioned"] = mentions
        resp = self._client.post(f"/message/sendText/{self.instance}", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ---- Ciclo de vida ------------------------------------------------------
    def close(self) -> None:
        """Fecha o pool de conexões HTTP. Seguro chamar mais de uma vez."""
        if not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> "EvolutionClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# ---- Instância compartilhada ------------------------------------------------
# Um servidor MCP atende uma instância da Evolution, então um cliente basta. Criar
# sob demanda (e não no import) mantém o erro de configuração próximo do uso, em vez
# de derrubar o servidor na subida.
_client_lock = threading.Lock()
_shared_client: Optional[EvolutionClient] = None


def get_client() -> EvolutionClient:
    """Devolve o :class:`EvolutionClient` compartilhado, criando-o na primeira chamada."""
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:  # confere de novo já com o lock
                _shared_client = EvolutionClient()
    return _shared_client


def close_client() -> None:
    """Fecha e descarta o cliente compartilhado (usado no encerramento e nos testes)."""
    global _shared_client
    with _client_lock:
        if _shared_client is not None:
            _shared_client.close()
            _shared_client = None


atexit.register(close_client)
