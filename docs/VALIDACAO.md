# Validação da implementação 0.1.0

## OAuth remoto

Validação da migração do modo HTTP para OAuth 2.1/OIDC:

- `.venv/bin/pytest -q`: **163 testes aprovados**, todos com dados e chaves sintéticos.
- Ruff lint/formato, Mypy e o contrato OpenAPI local aprovados.
- Tokens RSA/ES256 válidos; issuer, audience, subject, client ID, escopo, expiração e `nbf`
  inválidos são recusados.
- Discovery OIDC/RFC 8414, cache JWKS, rotação de `kid`, algoritmo fixo, bloqueio de `jku`/`x5u`
  e indisponibilidade do provedor exercitados sem rede externa.
- Integração ASGI confirma Protected Resource Metadata, desafios `WWW-Authenticate`, 401/403,
  headers duplicados, Host/Origin, health público e execução das 21 tools com token válido.
- O subprocesso `stdio` continua iniciando e encerrando sem OAuth ou listener.
- O smoke do container passa a verificar a fronteira OAuth sem exigir provedor real; build e scan
  da imagem permanecem como gates do GitHub Actions porque o daemon Docker local está inativo.
- Nenhuma credencial, conta real, provedor OIDC ou infraestrutura remota foi criado ou acessado.

## Evolução atual — sincronização manual

Validação local desta alteração, com o ambiente `.venv` existente (o executável `uv`
não estava disponível no PATH):

- `.venv/bin/pytest -q`: **132 testes aprovados**, com HTTP Pluggy simulado.
- Ruff lint e formato: aprovados; Mypy: aprovado nos 20 módulos de produção.
- `scripts/check_openapi_drift.py`: snapshot e catálogo local válidos; PATCH de Item
  classificado como habilitado e sujeito à verificação de drift.
- `scripts/smoke_stdio.py --mock`: **21 tools descobertas**, consultas sintéticas aprovadas.
- Testes de transporte confirmam schemas iguais em stdio/HTTP e compatibilidade das consultas.
- Cobertura nova: API Key compartilhada, 401, múltiplos Items, polling, timeout, execução
  existente/concorrente, restrições, 403, 429, falha de rede, MFA, login, OUTDATED,
  sucesso parcial, logs sanitizados e ausência de PATCH nas consultas.
- Nenhuma conta real sincronizada, nenhum perfil/memória Hermes modificado, nenhum commit.
- Testes reais de plano, instituição e memória em nova sessão seguem o roteiro do README.
  Não foram repetidos build/container, auditoria de dependências ou comparação remota;
  os resultados abaixo pertencem à versão anterior.

Arquivos de produção alterados: `config.py`, `server.py`, `errors.py`, `client/http.py`,
`client/responses.py`, `policy/item_scope.py` e `tools/raw.py`; novo `sync.py`.
Todos ficam em `src/pluggy_finance_mcp/`. O `PluggyAuth` existente foi mantido como gerenciador
de chave em memória; o novo serviço concentra a decisão de atualizar e o polling.
O escopo de recursos passou a ser construído com o UUID de cada chamada.

Testes alterados: `conftest.py`, `test_contract.py`, `test_raw_security.py`,
`test_semantic.py`, `test_transports.py`; novo `test_sync.py` (todos em `tests/`).
Configuração/documentação alterada: `.env.example`, `README.md`, `CHANGELOG.md`,
`deploy/cloud-run.yaml`, `openapi/classifications.json`, `scripts/openapi_catalog.py`,
`scripts/smoke_stdio.py`, `scripts/smoke_container.sh` e os documentos
`OPERACAO_LOCAL.md`, `SEGURANCA.md`, `ENDPOINTS_PLUGGY.md`, `ESPECIFICACAO_TECNICA.md`,
`DEPLOY_CLOUD_RUN.md` e este arquivo em `docs/`.

## Registro histórico da versão anterior

Verificações executadas em 2026-09-14, sem credenciais ou dados financeiros reais:

| Verificação | Resultado |
|---|---|
| Pytest em Python 3.13.5 | 96 testes aprovados |
| Pytest em Python 3.12.14 | 96 testes aprovados |
| Ruff lint e formato | aprovados |
| Mypy | aprovado, 19 módulos |
| Contrato e inventário OpenAPI | aprovados |
| Comparação do OpenAPI remoto | nenhuma operação adicionada, removida ou alterada |
| Auditoria das dependências de produção (`pip-audit`) | nenhuma vulnerabilidade conhecida encontrada |
| Build Python | wheel e sdist gerados; wheel contém apenas pacote e metadata |
| MCP stdio e Streamable HTTP | schemas iguais e 18 tools executadas com fixtures sintéticas |
| Ambiente Python/SDK do Hermes 0.21.2 | descoberta das 18 tools e chamadas sintéticas aprovadas |
| Configuração real do perfil Hermes | não alterada |
| Consultas financeiras reais | não executadas; dependem das credenciais e do Item autorizado |
| Docker build, scan e smoke do container | aprovados no GitHub Actions; daemon Docker local inativo |
| Cloud Run / Secret Manager | templates entregues; nenhum recurso criado ou deploy realizado |

O teste do ambiente Hermes usa o cliente MCP instalado no mesmo Python do Hermes e inicia
um subprocesso de teste deste projeto. Não substitui uma conversa real com o agente depois de
configurar as credenciais. O funcionamento local do MCP não depende de Docker.

Para reproduzir: `make check`, `make audit`, `make openapi-check` e, opcionalmente com Docker
ativo, `make container container-smoke`. O container continua opcional para uso local.

## Revisão para publicação pública

- Exemplos e snippets upstream removidos do snapshot; hashes original e publicado separados.
- `Connector.productCoverage`: campo opcional revisado, sem ampliar projeções de resposta.
- `GET /items/{id}/resources` e seus três schemas: classificados fora do escopo.
- `PaymentIntentStatus.PAYMENT_TIMEOUT`: alteração revisada no domínio de pagamentos excluído.
- As 12 operações GET autorizadas e as 18 tools mantêm seus contratos públicos.
- Gitleaks 8.30.1: nenhum segredo detectado nos 55 arquivos selecionados, no commit inicial
  antes do push e no histórico publicado. Não há exceções adicionais.
- Autor e committer usam `gabrielbssantos` e o e-mail GitHub `noreply` configurado só neste repo.
- `.env`, ambientes virtuais, caches, logs e artefatos de build permanecem ignorados.

## Evidência do CI público

[Execução aprovada após a correção da imagem base](https://github.com/gabrielbssantos/pluggy-finance-mcp/actions/runs/34860537598),
commit `9bac23b4baddb12e1efbd2af789f188cef4e02a7`: Python 3.12 e 3.13, contrato remoto,
scanner de segredos e container aprovados.

O primeiro scan identificou 12 vulnerabilidades HIGH/CRITICAL com correção disponível em
pacotes Debian da imagem base. O Dockerfile aplica as atualizações disponíveis antes dos
estágios de build e execução; a nova imagem passou pelo mesmo scan e smoke HTTP.
O Trivy bloqueia HIGH/CRITICAL com correção disponível; a aprovação não implica ausência de
vulnerabilidades de outras severidades ou ainda sem correção. As dependências Python de
produção e desenvolvimento também passaram pelo `pip-audit` local.

[Histórico completo das execuções](https://github.com/gabrielbssantos/pluggy-finance-mcp/actions/workflows/ci.yml).
