import re

from evolution_client import get_client

DDI_BRASIL = "55"


def normalizar_destino(destino: str) -> str:
    """Garante o código do país em números brasileiros; JIDs passam intactos.

    Um JID (`...@g.us`, `...@s.whatsapp.net`) já é um endereço completo. Números
    soltos vêm como DDD + número (10 ou 11 dígitos) e precisam do 55 na frente.
    """
    if not destino or "@" in destino:
        return destino
    digitos = re.sub(r"\D", "", destino)
    if len(digitos) in (10, 11):
        return DDI_BRASIL + digitos
    return digitos


class SendGiuliaAI:
    """Envio de mensagens pela Evolution API.

    Reaproveita o cliente HTTP compartilhado; o parâmetro existe para injetar um
    dublê nos testes.
    """

    def __init__(self, client=None):
        self.client = client or get_client()

    def textMessage(self, recipient: str, message: str, mentions=None) -> dict:
        """Envia uma mensagem de texto REAL via Evolution API.

        recipient: número (ex.: 5511999999999) ou JID de grupo (...@g.us). Números
        sem código do país recebem o 55 — antes essa normalização só existia como
        instrução no docstring da tool, ou seja, dependia de o LLM lembrar.

        Devolve a resposta da Evolution (contém `key.id`, o id da mensagem). Lança
        exceção em caso de falha HTTP, tratada pela tool no servidor MCP.
        """
        return self.client.send_text(
            normalizar_destino(recipient), message, mentions=mentions
        )
