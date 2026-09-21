# Implantação remota com OAuth

O modo remoto expõe o MCP por Streamable HTTP e exige OAuth 2.1/OIDC. Ele pode ser hospedado em
Cloud Run, Kubernetes, uma VM ou outra plataforma que forneça HTTPS. O servidor não implementa
tela de login, cadastro de usuários, endpoint de autorização nem emissão de tokens.

## Arquitetura

1. GPT, Claude ou Hermes acessa a URL pública do MCP.
2. O MCP responde com o desafio e os metadados do recurso protegido.
3. O cliente abre o fluxo Authorization Code com PKCE `S256` no provedor OIDC.
4. O usuário faz login; o provedor emite um access token JWT para a audience do MCP.
5. O cliente envia esse token em `Authorization: Bearer` e o MCP valida todas as claims.

O provedor pode oferecer login pelo Google. Nesse caso, Google confirma a identidade para o
provedor, mas não recebe credenciais Pluggy. Não use um ID token genérico do Google no lugar de
um access token emitido especificamente para a API do MCP.

## Provedor OIDC

Configure no Auth0, Keycloak, Zitadel ou equivalente:

- issuer HTTPS com metadata OIDC ou OAuth Authorization Server Metadata e `jwks_uri` HTTPS;
- uma API/resource cuja audience seja exatamente a URL pública, incluindo `/mcp`;
- escopo `pluggy:access`;
- Authorization Code e PKCE `S256`; desabilite implicit grant e password grant;
- um client separado para GPT, Claude e Hermes, com redirect URI exata e sem wildcard;
- refresh-token rotation quando o cliente e o provedor utilizarem refresh tokens;
- cadastro dinâmico de clientes desabilitado, pois esta implantação usa client IDs previamente
  registrados.

Copie o identificador estável `sub` do usuário no painel do provedor ou de um token inspecionado
localmente. Não use e-mail como subject: ele pode mudar. Copie também os três client IDs para a
allowlist do MCP. Client secrets, quando exigidos por um cliente confidencial, ficam no cliente e
no provedor; nunca no MCP.

## Ambiente do servidor

```dotenv
PLUGGY_CLIENT_ID=<secret-no-servidor>
PLUGGY_CLIENT_SECRET=<secret-no-servidor>
MCP_TRANSPORT=streamable-http
MCP_AUTH_MODE=oauth
MCP_PUBLIC_URL=https://finance.example.com/mcp
MCP_ALLOWED_HOSTS=finance.example.com
MCP_OAUTH_ISSUER_URL=https://identity.example.com
MCP_OAUTH_ALLOWED_SUBJECT=provider|identificador-estavel
MCP_OAUTH_ALLOWED_CLIENT_IDS=gpt-client,claude-client,hermes-client
MCP_OAUTH_SCOPE=pluggy:access
MCP_OAUTH_SIGNING_ALGORITHM=RS256
PORT=8080
```

`MCP_PUBLIC_URL` é simultaneamente o resource identifier e a audience exigida. Use `ES256`
somente quando o provedor estiver configurado para assinar access tokens com esse algoritmo.
Tokens opacos e introspecção não são suportados.

## Conexão dos clientes

Cadastre a redirect URI exibida por cada cliente no respectivo registro OAuth. Depois, adicione
`https://finance.example.com/mcp` como servidor Streamable HTTP e informe o client ID previamente
registrado. A interface pode exibir **Authenticate**, **Connect** ou iniciar o login no primeiro
uso. O navegador abre o provedor; depois do consentimento, o cliente guarda o token e o renova
conforme sua própria implementação.

## Operação segura

- Restrinja tráfego à porta HTTPS pública e não exponha diretamente a porta interna do processo.
- Não use wildcard em hosts, origens ou redirect URIs.
- Mantenha access tokens curtos, MFA no provedor e revogação individual por client ID.
- Monitore respostas 401/403 e volume anormal sem registrar tokens ou claims.
- Rotacione chaves no provedor mantendo sobreposição suficiente no JWKS.
- `/healthz`, `/readyz` e os metadados OAuth são públicos e não contêm dados financeiros.
- Não coloque Pluggy secrets, OAuth client secrets ou tokens em imagem, YAML ou Git.

Antes de liberar tráfego, execute `make check`, `make audit` e o smoke test do container. Faça uma
conexão real por vez e confirme que tokens com outro subject, client ID ou audience são recusados.
