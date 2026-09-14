# Validação da implementação 0.1.0

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
| Docker build, scan e smoke do container | preparados no CI, não executados localmente: daemon Docker inativo |
| Cloud Run / Secret Manager / publicação | templates entregues; nenhum recurso criado ou deploy realizado |

O teste do ambiente Hermes usa o cliente MCP instalado no mesmo Python do Hermes e inicia
um subprocesso de teste deste projeto. Não substitui uma conversa real com o agente depois de
configurar as credenciais. O funcionamento local do MCP não depende de Docker.

Para reproduzir: `make check`, `make audit`, `make openapi-check` e, opcionalmente com Docker
ativo, `make container container-smoke`. Os jobs GitHub Actions só executarão quando o projeto
for publicado em um repositório com Actions habilitado.

## Revisão para publicação pública

- Exemplos e snippets upstream removidos do snapshot; hashes original e publicado separados.
- `Connector.productCoverage`: campo opcional revisado, sem ampliar projeções de resposta.
- `GET /items/{id}/resources` e seus três schemas: classificados fora do escopo.
- `PaymentIntentStatus.PAYMENT_TIMEOUT`: alteração revisada no domínio de pagamentos excluído.
- As 12 operações GET autorizadas e as 18 tools mantêm seus contratos públicos.
- Gitleaks no CI verifica todo o histórico, sem exceções adicionais; nenhum dado real é usado.
