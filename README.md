# PRJ-06 — WhatsApp via Evolution API (servidor MCP)

Servidor **MCP** (FastMCP, `stdio`) que dá a um agente LLM *tools* para operar o WhatsApp
através da **Evolution API** (gateway self-hosted). Corresponde ao **Capítulo 7** do livro
*Model Context Protocol* (Sandeco).

As implementações mock originais (grupos/mensagens fake e envio via `print`) foram
substituídas por chamadas **reais** à Evolution API (`src/evolution_client.py`).

## Tools

| Tool | Endpoint Evolution | O que faz |
|---|---|---|
| `get_groups` | `GET /group/fetchAllGroups/{instance}` | Lista os grupos reais da instância. |
| `get_group_messages(group_id, start, end)` | `POST /chat/findMessages/{instance}` | Histórico de um grupo (recorte por data feito client-side). |
| `send_message_to_group(group_id, message)` | `POST /message/sendText/{instance}` | Envia texto a um grupo (`...@g.us`). |
| `send_message_to_phone(cellphone, message)` | `POST /message/sendText/{instance}` | Envia texto a um número (`5511...`). |

## Configuração

Requer uma instância **Evolution API** rodando com um número de WhatsApp pareado.

```bash
uv sync
cp .env.example .env     # preencha com os dados da SUA instância
uv run python src/evoapi_mcp.py   # ou: uv run python src/main.py
```

Variáveis (`.env`, fora do git):

| Variável | Descrição |
|---|---|
| `EVOLUTION_BASE_URL` | URL do servidor Evolution (ex.: `http://host:8080`) |
| `EVOLUTION_API_KEY` | API key (header `apikey`) |
| `EVOLUTION_INSTANCE` | Nome da instância pareada |

> Testado contra **Evolution API v2**. Conforme a versão, algum nome de campo na resposta
> (ex.: `subject`, `pushName`, formato de `findMessages`) pode variar — o cliente já
> normaliza os formatos mais comuns.

## Ciclo de vida do cliente HTTP

O `EvolutionClient` é **compartilhado** entre as tools, via `get_client()`.

Antes, cada chamada de tool instanciava `GroupController()` → `EvolutionClient()` →
um `httpx.Client` novo que nunca era fechado. Num servidor MCP de vida longa isso vaza
um pool de conexões por chamada: 10 chamadas, 10 pools abertos.

Como o servidor atende uma única instância da Evolution, um cliente reaproveitado é o
formato correto — mantém o keep-alive e não acumula sockets. A criação é preguiçosa
(o erro de configuração aparece no primeiro uso, não na subida do servidor) e
`close_client()` está registrado em `atexit`.

`GroupController` e `SendGiuliaAI` aceitam um cliente injetado, o que permite testar
sem rede.

## Testes

```bash
uv run pytest        # 35 testes, sem tocar a rede (httpx.MockTransport)
```

Cobrem o reuso do cliente, o fechamento do pool, a validação de configuração, a
normalização dos formatos de resposta da Evolution, a extração de texto por tipo de
mensagem e o recorte por data.
