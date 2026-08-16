from datetime import datetime

from group import Group
from message_giulia_ai import MessageGiuliaAI
from evolution_client import get_client, _extract_text


class GroupController:
    """Operações de grupo sobre a Evolution API.

    O cliente é injetável para permitir teste sem rede; por padrão usa o cliente
    compartilhado do módulo, em vez de abrir um pool HTTP novo a cada chamada de tool.
    """

    def __init__(self, client=None):
        self.client = client or get_client()

    def fetch_groups(self):
        """Busca os grupos REAIS da instância via Evolution API."""
        return [
            Group(group_id=g.get("id"), name=g.get("subject", ""))
            for g in self.client.fetch_all_groups()
        ]

    def get_messages(self, group_id: str, start_date: str, end_date: str):
        """Busca mensagens REAIS de um grupo e filtra pelo intervalo.

        O recorte por data é feito client-side: o endpoint `findMessages` da Evolution
        não expõe filtro por período, então buscamos as mensagens do grupo e filtramos
        aqui.
        """
        fmt = "%Y-%m-%d %H:%M:%S"
        start_ts = datetime.strptime(start_date, fmt).timestamp()
        end_ts = datetime.strptime(end_date, fmt).timestamp()

        messages = []
        for m in self.client.find_messages(group_id):
            ts = int(m.get("messageTimestamp", 0))
            if not (start_ts <= ts <= end_ts):
                continue
            messages.append(MessageGiuliaAI({
                "push_name": m.get("pushName", "Unknown"),
                "message_timestamp": ts,
                "message_type": m.get("messageType", "text"),
                "text": _extract_text(m.get("message")),
            }))
        return messages
