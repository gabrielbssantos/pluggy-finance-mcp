# Pluggy Finance MCP

Servidor MCP pessoal em Python para múltiplas conexões Pluggy em uma única instância.
Implementa consultas, agregações financeiras e sincronização explícita sob demanda,
com isolamento por Item em cada chamada, paginação e proteção de credenciais.

Implementação independente voltada a consultas financeiras pessoais no Hermes; não é um
produto oficial da Pluggy. Existem também o [MCP da Pluggy](https://github.com/pluggyai/pluggy-mcp)
e o [mcp-pluggy comunitário](https://github.com/lefranchi/mcp-pluggy).

**O uso local não precisa de Docker.** O Hermes inicia diretamente o processo Python por
`stdio`. O container é opcional e serve para uma futura implantação no Cloud Run.

## Execução local

Requisitos: Python 3.12+ e [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --frozen
cp .env.example .env
```

Preencha apenas `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET` em `.env`.
A autorização inicial no MeuPluggy deve ter sido feita previamente. O servidor não cria Items.

```bash
uv run --env-file .env python -m pluggy_finance_mcp
```

O processo aguarda mensagens MCP em stdin; não abre interface gráfica ou porta de rede.
`.env` só é carregado quando solicitado explicitamente ao `uv`. A aplicação lê o ambiente.
Depois da instalação, `.venv/bin/python -m pluggy_finance_mcp` também funciona com as variáveis
já exportadas. Veja a [configuração do Hermes](docs/OPERACAO_LOCAL.md).

## Tools

Todas as 21 tools exigem `item_id` (UUID), além dos parâmetros abaixo.

| Conexão e sincronização | Parâmetros adicionais |
|---|---|
| `get_item` | nenhum; valida existência e consulta estado/freshness |
| `get_sync_status` | nenhum; consulta andamento, sem PATCH |
| `sync_item` | `wait=true`, `timeout_seconds?` (1–3600) |

| Consultas básicas | Parâmetros |
|---|---|
| `get_connection_status` | nenhum |
| `list_accounts` | `type?`, `subtype?` (filtro local) |
| `get_account` | `account_id` |
| `get_account_balance` | `account_id` |
| `list_account_statements` | `account_id` |
| `list_transactions` | `account_id`, `date_from?`, `date_to?`, `cursor?` |
| `get_transaction` | `transaction_id` |
| `list_credit_card_bills` | `account_id` |
| `get_credit_card_bill` | `bill_id` |
| `list_investments` | `type?`, `page=1`, `page_size=100` |
| `get_investment` | `investment_id` |
| `list_investment_transactions` | `investment_id`, `page=1`, `page_size=100` |

| Agregações | Parâmetros |
|---|---|
| `get_total_balance` | `account_ids?` |
| `get_monthly_expenses` | `month?` **ou** `date_from` e `date_to`; `account_ids?` |
| `get_expenses_by_category` | mesmos parâmetros de gastos mensais |
| `get_credit_card_summary` | `account_ids?` |
| `get_investment_portfolio` | `investment_ids?` |
| `get_net_worth` | `account_ids?`, `investment_ids?` |

Nenhuma tool aceita credenciais, URL ou método HTTP. Identity não está implementada.
Datas de intervalo usam `YYYY-MM-DD`; mês usa `YYYY-MM`. O padrão das agregações de gastos é
mês atual em `America/Sao_Paulo`, pelo lançamento de cada transação.

As respostas têm `ok`, `tool`, `data`, `pagination`, `meta`, `warnings` e `error`.
Totais calculados com Decimal são strings decimais; campos brutos mantêm seus nomes e valores
numéricos JSON. Verifique `meta.complete` e `warnings` antes de interpretar uma agregação.
As [regras de cálculo](docs/AGREGACOES.md) descrevem cobertura, ambiguidades e limites.

## Pluggy authentication

`PLUGGY_CLIENT_ID` + `PLUGGY_CLIENT_SECRET` → `POST /auth` → API Key temporária.
O gerenciador compartilha a chave entre todas as conexões, somente em memória, e a renova
15 minutos antes da expiração de duas horas. Um HTTP 401 permite uma renovação e repetição;
um segundo 401 encerra a chamada. Não configure `PLUGGY_API_KEY` nem persista chaves em disco.

## Item IDs

Cada conexão tem seu próprio `itemId`. Forneça-o ao Hermes no primeiro uso e peça que guarde
a associação, por exemplo `pluggy.itau_pessoal → <UUID>`. O Hermes pode validar com `get_item`.
Nas próximas sessões ele resolve o nome na memória e fornece o UUID em cada chamada.
Uma única instância e as mesmas credenciais atendem Itaú, Nubank, Inter e outras conexões.

O MCP não lê nem escreve `MEMORY.md`, não mantém registry, banco local ou aliases, e não
depende da memória do Hermes para funcionar. Não há Item em variável de ambiente.
Migração: as antigas tools agora também exigem `item_id`; o vínculo de contas, transações
e investimentos continua sendo validado contra o Item recebido naquela chamada.

## Manual synchronization

Consultas nunca chamam PATCH. “Quanto gastei hoje?” consulta os dados já disponíveis.
“Atualize meu Itaú e veja quanto gastei hoje” exige `sync_item` antes da consulta.

`sync_item(item_id, wait=true)` valida o Item, reutiliza as credenciais guardadas pela Pluggy
com `PATCH /items/{id}` e corpo `{}`, e acompanha o estado por polling. Um Item já atualizando
é acompanhado sem novo PATCH. `wait=false` retorna imediatamente após validação/envio.
`get_sync_status(item_id)` e `get_item(item_id)` permitem verificar depois, incluindo `lastUpdatedAt`.

Configurações opcionais: `PLUGGY_SYNC_POLL_INTERVAL_SECONDS=3` e
`PLUGGY_SYNC_TIMEOUT_SECONDS=120`. O prazo inclui validação, envio, retries e polling.
Timeout local com execução iniciada retorna `data.inProgress=true`; não significa falha do banco.
Falha de rede após envio pode deixar o resultado incerto; consulte o status antes de reenviar.

O envelope `ok=true` indica que a tool produziu um resultado, não que o banco sincronizou:
verifique `data.success`, `data.inProgress`, `data.requiresUserAction` e `data.error`.
Sucesso parcial é sinalizado por `partialSuccess=true`, sem afirmar atualização completa.
MFA, login inválido e renovação de parâmetros exigem intervenção via Pluggy Connect;
o MCP não pede senha ou token. `OUTDATED` pode ser atualizado mediante pedido explícito.

Restrições de plano/frequência e connector offline preservam códigos específicos e mensagens
seguras; não causam repetição de PATCH. HTTP 403 não é repetido. HTTP 429 respeita Retry-After
com até duas repetições; se a espera exceder o limite HTTP, devolve o erro e a espera indicada.
Mensagens livres da API não são expostas, pois podem conter credenciais. A frequência mínima
é retornada quando existe em campo numérico estruturado; a próxima data só é calculada com
timestamp e fuso conhecidos. Não se infere frequência de texto livre.

Não há scheduler, cron, sync_all ou descoberta de Items. A Pluggy pode executar auto-sync
por configuração própria; este MCP não altera essa configuração. Confira o
[ciclo do Item](https://docs.pluggy.ai/docs/item-lifecycle) e as
[restrições de atualização](https://docs.pluggy.ai/reference/items).

## Example

Primeiro uso: “Meu Itaú pessoal possui itemId <uuid>. Lembre disso.”
Depois: “Verifique quando meu Itaú foi atualizado.” → memória Hermes → `get_item(item_id)`.
Depois: “Atualize meu Itaú.” → memória Hermes → `sync_item(item_id)` → Pluggy.
Para atualizar dois bancos, o Hermes chama `sync_item` individualmente, inicialmente em sequência.

## Teste manual com uma conexão real

1. Inicie o MCP por stdio e forneça ao Hermes um UUID real.
2. Chame `get_item` e confira connector, status e `lastUpdatedAt`.
3. Solicite uma única atualização com `sync_item`; se ainda estiver em andamento, use `get_sync_status`.
4. Consulte `get_item` novamente e compare o timestamp. Consulte contas/transações normalmente.
5. Em uma nova sessão Hermes, peça o estado pelo nome do banco e confirme que a memória resolve o UUID.

Os testes automatizados não executam essas etapas com contas reais. Sem um Item real fornecido
para teste, a validação de plano, instituição, MFA e memória entre sessões permanece manual.

## Validação e desenvolvimento

```bash
make check     # lint, formato, tipos, contratos e testes; não precisa de Docker
make audit     # auditoria de dependências
make openapi-check  # compara o snapshot com a API pública, sem credenciais
```

Os testes usam dados sintéticos e HTTP simulado para a Pluggy. Testes MCP exercitam subprocessos
`stdio` e HTTP real em loopback; não consultam dados financeiros reais.

## HTTP e Cloud Run opcionais

O mesmo registro de tools atende `/mcp` por Streamable HTTP. Para testar fora de Docker,
configure `MCP_TRANSPORT=streamable-http`, `MCP_AUTH_MODE=bearer` e `MCP_BEARER_TOKEN` aleatório
com pelo menos 32 caracteres. `/healthz` e `/readyz` não consultam a Pluggy.

O [guia Cloud Run](docs/DEPLOY_CLOUD_RUN.md) explica o container, Secret Manager e hosts permitidos.
Não há deploy automático ou infraestrutura criada. OAuth e conexão com ChatGPT ficam para
uma versão futura; esta versão remota usa bearer token estático.

## Documentação

- [Operação local e Hermes](docs/OPERACAO_LOCAL.md)
- [Regras das agregações](docs/AGREGACOES.md)
- [Segurança e contratos](docs/SEGURANCA.md)
- [Resultados da validação](docs/VALIDACAO.md)
- [Cloud Run opcional](docs/DEPLOY_CLOUD_RUN.md)
- [Inventário OpenAPI gerado](docs/ENDPOINTS_PLUGGY.md)
- [Especificação original e decisões da implementação](docs/ESPECIFICACAO_TECNICA.md)

O SDK oficial MCP está fixado na linha 1.x mantida (`mcp>=1.28,<2`, lock em 1.30.0).
A atualização para 2.x requer migração explícita e os mesmos testes de transporte.
