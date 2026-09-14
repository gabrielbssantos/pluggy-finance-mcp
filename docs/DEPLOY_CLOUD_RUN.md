# HTTP e Cloud Run opcionais

O MCP local funciona diretamente em Python. Docker só é necessário se você quiser construir
uma imagem para hospedagem remota. Este projeto entrega o template; não cria recursos cloud.

## Teste HTTP sem Docker

Configure em um arquivo `.env` ignorado pelo Git as credenciais e:

```dotenv
MCP_TRANSPORT=streamable-http
MCP_AUTH_MODE=bearer
MCP_BEARER_TOKEN=<token-aleatorio-com-pelo-menos-32-caracteres>
MCP_ALLOWED_HOSTS=localhost,127.0.0.1
PORT=8080
```

Gere o token com um gerenciador de senhas ou `secrets.token_urlsafe(32)` e guarde como secret.
Execute `uv run --env-file .env python -m pluggy_finance_mcp`.

- `GET /healthz` e `GET /readyz`: públicos, sem chamadas à Pluggy.
- `/mcp`: requer `Authorization: Bearer <token>` em todas as chamadas.
- O processo escuta `0.0.0.0:$PORT`. Use loopback para desenvolvimento e HTTPS em acesso remoto.
- Origem e Host são validados. Não use wildcard nos hosts permitidos.

O HTTP é stateless no protocolo MCP; múltiplas instâncias têm seus próprios caches de API Key.
Não há sessão financeira persistente ou necessidade de sticky session.

## Imagem opcional

Com Docker ativo:

```bash
docker build --platform linux/amd64 -t pluggy-finance-mcp:local .
bash scripts/smoke_container.sh pluggy-finance-mcp:local
```

O smoke test usa valores sintéticos, testa health checks, autenticação, descoberta das 18 tools
e execução sem root. Não chama a Pluggy. A imagem contém apenas runtime e pacote; testes,
`.env`, snapshot OpenAPI e credenciais não fazem parte do contexto de build permitido.

A execução do build/scan/smoke também está definida como job separado no GitHub Actions.
O desenvolvimento e `make check` não dependem de Docker.

## Preparação do Cloud Run

Antes de publicar, escolha projeto e região e prepare:

1. Um repositório Artifact Registry e a imagem linux/amd64 referenciada por digest.
2. Uma conta de serviço exclusiva para este serviço.
3. Secrets `pluggy-client-id`, `pluggy-client-secret`, `pluggy-item-id` e
   `pluggy-mcp-bearer-token`; conceda à conta de serviço acesso apenas a esses secrets.
4. Cópia de `deploy/cloud-run.yaml`, preenchendo projeto, imagem, conta, versões dos secrets
   e o hostname HTTPS real. Nenhum segredo em texto deve entrar no YAML ou imagem.

O template sugere 1 CPU, 512 MiB, 0–2 instâncias, concorrência 20 e timeout 60 segundos;
as tools têm deadline interno de até 45 segundos. As probes TCP evitam conflito com Host
validation das probes internas. As rotas HTTP de saúde continuam disponíveis para monitoração.

O hostname real pode ser obtido de uma primeira revisão sem tráfego e ajustado antes de conectar
um cliente. Mantenha autenticação por bearer em todas as revisões. Scale-to-zero implica cold start.

Se optar por deixar a invocação Cloud Run acessível pela internet, a autorização será aplicada
pelo próprio MCP. Se exigir IAM do Cloud Run, o cliente precisará fornecer também a credencial
IAM por um mecanismo compatível (por exemplo `X-Serverless-Authorization`), preservando o bearer
MCP no header `Authorization`. Essa escolha e a publicação não são executadas por este projeto.

Rotação de secrets exige uma nova revisão usando a versão nova. Revogue tokens anteriores no
mesmo processo de rollout; não há lista dinâmica de tokens no servidor.

## Limite desta versão

Bearer estático atende clientes que permitem configurar headers, incluindo o modo remoto do
Hermes. Não implementa OAuth, Protected Resource Metadata ou login do ChatGPT. A integração
ChatGPT exigirá uma nova etapa com provedor OAuth e validação de issuer, audience, expiração e
escopo pela interface `TokenValidator`.

Referências: [Cloud Run](https://cloud.google.com/run/docs),
[secrets no Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets),
[contrato do container](https://cloud.google.com/run/docs/container-contract).
