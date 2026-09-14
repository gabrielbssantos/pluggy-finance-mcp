# Pluggy Finance MCP

Servidor MCP pessoal em Python, **somente leitura e restrito a um único Item MeuPluggy**.
Implementa 12 consultas básicas e 6 agregações financeiras, com isolamento de recursos,
paginação explícita e proteção de credenciais.

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

Preencha `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET` e `PLUGGY_ITEM_ID` em `.env`.
A autorização inicial no MeuPluggy deve ter sido feita previamente. O servidor não cria Items.

```bash
uv run --env-file .env python -m pluggy_finance_mcp
```

O processo aguarda mensagens MCP em stdin; não abre interface gráfica ou porta de rede.
`.env` só é carregado quando solicitado explicitamente ao `uv`. A aplicação lê o ambiente.
Depois da instalação, `.venv/bin/python -m pluggy_finance_mcp` também funciona com as variáveis
já exportadas. Veja a [configuração do Hermes](docs/OPERACAO_LOCAL.md).

## Tools

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

Nenhuma tool aceita `item_id`, credenciais, URL ou método HTTP. Identity não está implementada.
Datas de intervalo usam `YYYY-MM-DD`; mês usa `YYYY-MM`. O padrão das agregações de gastos é
mês atual em `America/Sao_Paulo`, pelo lançamento de cada transação.

As respostas têm `ok`, `tool`, `data`, `pagination`, `meta`, `warnings` e `error`.
Totais calculados com Decimal são strings decimais; campos brutos mantêm seus nomes e valores
numéricos JSON. Verifique `meta.complete` e `warnings` antes de interpretar uma agregação.
As [regras de cálculo](docs/AGREGACOES.md) descrevem cobertura, ambiguidades e limites.

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
