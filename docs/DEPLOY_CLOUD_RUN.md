# HTTP e Cloud Run opcionais

O MCP local funciona diretamente em Python. Docker só é necessário se você quiser construir
uma imagem para hospedagem remota. Este projeto entrega o template; não cria recursos cloud.

## Teste HTTP sem Docker

Configure em um arquivo `.env` ignorado pelo Git as credenciais e:

```dotenv
MCP_TRANSPORT=streamable-http
MCP_AUTH_MODE=oauth
MCP_PUBLIC_URL=https://localhost/mcp
MCP_OAUTH_ISSUER_URL=https://identity.example.com
MCP_OAUTH_ALLOWED_SUBJECT=<subject-estavel>
MCP_OAUTH_ALLOWED_CLIENT_IDS=<client-id-de-teste>
MCP_ALLOWED_HOSTS=localhost,127.0.0.1
PORT=8080
```

Execute `uv run --env-file .env python -m pluggy_finance_mcp`.

- `GET /healthz` e `GET /readyz`: públicos, sem chamadas à Pluggy.
- `/mcp`: requer um access token JWT OAuth válido em todas as chamadas.
- `GET /.well-known/oauth-protected-resource/mcp`: metadata pública para os clientes.
- O processo escuta `0.0.0.0:$PORT`. Use loopback para desenvolvimento e HTTPS em acesso remoto.
- Origem e Host são validados. Não use wildcard nos hosts permitidos.

Esse teste inicia o processo e permite verificar health e metadata, mas uma chamada autenticada
exige um provedor OIDC real ou de desenvolvimento emitindo JWT para `https://localhost/mcp`.

O HTTP é stateless no protocolo MCP; múltiplas instâncias têm seus próprios caches de API Key.
Não há sessão financeira persistente ou necessidade de sticky session.

## Imagem opcional

Com Docker ativo:

```bash
docker build --platform linux/amd64 -t pluggy-finance-mcp:local .
bash scripts/smoke_container.sh pluggy-finance-mcp:local
```

O smoke test usa valores sintéticos, testa health checks, metadata, bloqueio sem token e execução
sem root. Não chama a Pluggy. A validação JWT e a descoberta das 21 tools são cobertas pela suíte
Python. A imagem contém apenas runtime e pacote; testes,
`.env`, snapshot OpenAPI e credenciais não fazem parte do contexto de build permitido.

A execução do build/scan/smoke também está definida como job separado no GitHub Actions.
O desenvolvimento e `make check` não dependem de Docker.

## Preparação do Cloud Run

Antes de publicar, escolha projeto e região e prepare:

1. Um repositório Artifact Registry e a imagem linux/amd64 referenciada por digest.
2. Uma conta de serviço exclusiva para este serviço.
3. Secrets `pluggy-client-id` e `pluggy-client-secret`; conceda à conta de serviço acesso apenas
   a esses secrets. Subject, issuer, audience e client IDs não são credenciais.
4. Cópia de `deploy/cloud-run.yaml`, preenchendo projeto, imagem, conta, versões dos secrets
   e as configurações OAuth. Nenhum segredo em texto deve entrar no YAML ou imagem.
5. Provedor OIDC preparado conforme [o guia remoto](DEPLOY_REMOTE.md), com audience igual à URL
   `run.app` completa terminada em `/mcp`.

O template sugere 1 CPU, 512 MiB, 0–2 instâncias, concorrência 20 e timeout 60 segundos;
as tools têm deadline interno de até 45 segundos. As probes TCP evitam conflito com Host
validation das probes internas. As rotas HTTP de saúde continuam disponíveis para monitoração.

O hostname real pode ser obtido de uma primeira revisão sem tráfego e ajustado antes de conectar
um cliente. Mantenha OAuth em todas as revisões. Scale-to-zero implica cold start.

Deixe a invocação Cloud Run acessível pela internet somente porque a autorização é aplicada pelo
próprio MCP. Se exigir IAM do Cloud Run, o cliente também precisará de uma credencial IAM por um
mecanismo compatível, preservando o access token OAuth do MCP no header `Authorization`. Nem todos
os clientes MCP suportam uma segunda credencial; valide essa opção antes de ativá-la.

Rotação de Pluggy secrets exige uma nova revisão usando a versão nova. Chaves de assinatura OAuth
são rotacionadas no provedor e publicadas no JWKS; mantenha a chave anterior durante a sobreposição.

## Limites desta versão

O servidor aceita somente access tokens JWT assinados em `RS256` ou `ES256`, conforme a
configuração. Tokens opacos e introspecção não são implementados. O projeto não cria o provedor,
os registros OAuth dos clientes, o domínio, os certificados ou o serviço Cloud Run.

Referências: [Cloud Run](https://cloud.google.com/run/docs),
[secrets no Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets),
[contrato do container](https://cloud.google.com/run/docs/container-contract).
