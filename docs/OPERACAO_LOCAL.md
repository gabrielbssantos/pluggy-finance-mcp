# Operação local e Hermes

Docker não participa do uso local. O Hermes inicia um subprocesso Python 3.12+ e troca
mensagens MCP por stdin/stdout. Logs operacionais seguros usam stderr.

## Instalação

Na raiz do projeto:

```bash
uv sync --frozen
cp .env.example .env
chmod 600 .env
```

Preencha os dois campos obrigatórios no arquivo ignorado pelo Git:
`PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET`.
Nunca use uma API Key temporária como credencial de configuração. Ela é obtida e renovada
em memória. O Item precisa pertencer à aplicação e estar autorizado no MeuPluggy previamente.

Teste a inicialização:

```bash
uv run --env-file .env python -m pluggy_finance_mcp
```

A espera silenciosa é normal: o processo aguarda um cliente MCP. Ctrl+D fecha stdin e encerra.
Uma configuração inválida encerra com código 2 e `CONFIGURATION_ERROR`, sem mostrar valores.

## Configuração do Hermes

A implementação instalada consultada foi Hermes 0.21.2. Seu transporte usa `command`, `args`,
`env` e `cwd` para criar `StdioServerParameters`, com interpolação `${VAR}` na configuração.

Adicione este bloco à configuração do seu perfil Hermes, substituindo os caminhos absolutos:

```yaml
mcp_servers:
  pluggy_finance:
    command: /CAMINHO/pluggy-finance-mcp/.venv/bin/python
    args: ["-m", "pluggy_finance_mcp"]
    cwd: /CAMINHO/pluggy-finance-mcp
    env:
      MCP_TRANSPORT: stdio
      MCP_AUTH_MODE: local_process
      PLUGGY_CLIENT_ID: "${PLUGGY_CLIENT_ID}"
      PLUGGY_CLIENT_SECRET: "${PLUGGY_CLIENT_SECRET}"
```

Inicie o Hermes com as duas credenciais carregadas pelo seu mecanismo de secrets. O Hermes
filtra o ambiente dos subprocessos; por isso os campos `env` acima são explícitos. Não coloque
valores reais no YAML versionado. O `.env` do projeto não é carregado automaticamente pelo Python.

Se preferir que o `uv` carregue `.env`, configure `command` com o caminho absoluto do executável
`uv`, `cwd` com a raiz deste projeto e:

```yaml
args: ["run", "--frozen", "--env-file", ".env", "python", "-m", "pluggy_finance_mcp"]
```

Nesse caso, omita do bloco `env` as duas credenciais interpoladas, para não sobrescrever o arquivo
com variáveis vazias. Mantenha apenas as configurações locais de transporte.

Esta implementação não altera sua configuração Hermes nem lê arquivos de credenciais.

## Uso

Forneça o `itemId` no primeiro uso e peça ao Hermes que lembre a associação ao banco em sua memória.
Comece com `get_item(item_id)` e `list_accounts(item_id)`. Todas as tools exigem `item_id`;
use os IDs retornados para detalhes. A memória pertence ao Hermes; o MCP não acessa `MEMORY.md`.
Para atualizar, solicite explicitamente `sync_item(item_id)`. Consultas não iniciam sincronização.
Após timeout ou `wait=false`, acompanhe com `get_sync_status(item_id)`.
Em `list_transactions`, envie `pagination.next_cursor` na próxima chamada junto com a mesma conta
e filtros. O servidor só extrai o cursor da resposta; nunca segue a URL de paginação upstream.
As páginas v2 têm até 500 registros e não aceitam `page_size`.

Faturas, contas e extratos não têm parâmetros de paginação documentados no snapshot atual.
Se o upstream indicar mais páginas, a resposta avisa incompletude sem inventar parâmetros.
Investimentos e suas movimentações usam `page` e `page_size` entre 1 e 500.

O saldo em tempo real pode não estar disponível para a instituição. Erros de suporte/consentimento
não são substituídos silenciosamente pelo saldo antigo; `get_account` fornece a posição coletada.

## Desenvolvimento

`make check` executa validação e testes sem Docker e sem credenciais reais.
`scripts/smoke_stdio.py` verifica descoberta no pacote instalado sem consultar a Pluggy.
A opção `--mock` também executa consultas básicas e agregações com fixtures sintéticas e requer dependências dev.
