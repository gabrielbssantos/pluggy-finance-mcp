# Changelog

## Não lançado — sincronização manual e múltiplos Items

- `get_item`, `get_sync_status` e `sync_item` explícito, com polling limitado e intervenção humana.
- Migração: todas as tools agora exigem `item_id`; removido o Item global do ambiente.
- Uma instância e autenticação em memória compartilhada; aliases pertencem à memória do Hermes.
- Códigos de restrição de plano/frequência preservados, retries limitados e PATCH sem credenciais.

## 0.1.0 — 2026-09-14

- 12 consultas Pluggy e 6 agregações, limitadas a um Item e somente leitura.
- MCP local por stdio e HTTP stateless com bearer, hosts/origens validados e health checks.
- Projeções de privacidade, autenticação em memória, deadlines e paginação explícita.
- Cálculos Decimal, moedas separadas, pendências, ambiguidades e lacunas de patrimônio visíveis.
- Snapshot OpenAPI sanitizado com hashes separados da fonte e do artefato publicado, inventário gerado, classificação de operações e detecção de drift.
- Testes sintéticos, documentação Hermes, CI e container opcional para Cloud Run.
- OAuth/ChatGPT, Identity e deploy permanecem fora desta versão.
