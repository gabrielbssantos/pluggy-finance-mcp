# Segurança e contratos

## Fronteiras

- Uma aplicação Pluggy, múltiplos Items; cada tool exige `item_id` validado como UUID.
- Allowlist fixa de 12 operações GET e `PATCH /items/{id}` exclusivo de `sync_item`, com corpo `{}`.
  O cliente de autenticação tem um único `POST /auth` interno.
- Host fixo `https://api.pluggy.ai`; nenhum redirect, proxy de ambiente ou URL fornecida pelo modelo.
- IDs são UUIDs. Contas e investimentos devem declarar o Item esperado; transações devem apontar
  para uma conta autorizada. Faturas exigem prova pela listagem de cartão autorizado antes do detalhe.
- Listagens conferem o vínculo dos registros quando ele é fornecido. Provas de vínculo vivem apenas
  durante a chamada da tool. Não há banco, cache externo, enumeração de Items ou Identity.
- A única mutação exposta é a sincronização explícita. Não há pagamentos ou executor HTTP genérico.
  `sync_item` tem readOnlyHint=false e idempotentHint=false. As anotações não substituem o bloqueio.

## Credenciais e dados

A API Key só existe em memória. A renovação ocorre 15 minutos antes do prazo de duas horas,
com lock concorrente; em `401`, uma renovação e repetição são permitidas. Há até duas repetições
GET para falhas transitórias, além da recuperação única de 401, dentro do deadline da tool.
PATCH só é repetido em 401 (uma vez) ou 429 (até duas vezes), nunca em timeout/5xx.
Retry-After é respeitado ou retornado ao chamador se exceder o limite da chamada. Autenticação
interna não é retentada automaticamente em falha de rede.

A projeção de resposta é uma allowlist explícita de campos. Remove owner, CPF, dados de conta,
credenciais de conector e dados pessoais de contrapartes. IDs necessários à navegação entre tools
continuam nas respostas, nunca nos logs. URLs assinadas de extrato são devolvidas apenas pela tool
específica e não são abertas pelo servidor.

Textos upstream são dados não confiáveis. Não alteram instruções, configuração, endpoints ou código.
O processo não executa comandos. Campos projetados mantêm nomes e valores; não há truncamento
silencioso. Respostas upstream e envelopes têm limite de 2 MB, ajustável até 10 MB.

## Transportes

`stdio` não abre listener. O proprietário controla o subprocesso e seu ambiente.
HTTP exige OAuth 2.1/OIDC e access token JWT. O verificador usa apenas metadata e JWKS do issuer
configurado, fixa o algoritmo assimétrico e recusa `jku`/`x5u` fornecidos pelo token. Assinatura,
issuer, audience, expiração, validade temporal, subject, client ID e escopo são verificados. O único
subject autorizado e os client IDs de GPT, Claude e Hermes formam allowlists explícitas.

O JWKS tem tamanho, quantidade de chaves e cache limitados; `kid` desconhecido permite atualização
controlada e falha de rede fecha o acesso. O SDK MCP publica Protected Resource Metadata e produz
desafios `WWW-Authenticate`. Headers Authorization duplicados são rejeitados. Hosts são explícitos,
origens não permitidas são bloqueadas, e `/healthz` e `/readyz` são públicos sem dados ou chamadas
Pluggy. O header Authorization, tokens, claims e identificadores OAuth nunca são logados.

O MCP não emite tokens nem recebe senha do usuário. Authorization Code, PKCE `S256`, consentimento,
MFA, refresh e revogação pertencem ao provedor OIDC e aos clientes. Tokens opacos e introspecção
estão fora do escopo atual.

## Erros e logs

Erros de execução usam envelope com `ok=false` e `error.code`, `error.retryable`. As falhas de
protocolo/validação de argumentos rejeitadas pelo SDK usam o erro MCP padrão. Erros internos não
expõem exceções, stack traces ou bodies upstream. Configuração inválida encerra com mensagem fixa.

Logs permitidos: nome da tool, sucesso, latência, quantidade de páginas, código de erro, UUID de
correlação gerado localmente e versão. Logs HTTP e de dependências são filtrados no entrypoint.
Não habilitar access logs com URLs ou headers ao integrar este ASGI em outro host.

## OpenAPI e CI

O snapshot publicado é sanitizado: exemplos e snippets upstream são removidos, preservando
operações, parâmetros, schemas e restrições. A serialização ordenada é determinística e
idempotente; a mesma transformação é aplicada na sincronização e na comparação remota.
`metadata.json` separa `source_sha256` (bytes originais, não publicados) de `snapshot_sha256`
(bytes sanitizados publicados), com versão da sanitização. O arquivo `.sha256` e o inventário
referem-se ao snapshot publicado. `classifications.json` contém a decisão explícita de
escopo de cada operação. O runtime usa sua própria allowlist e testes exigem equivalência.

`check_openapi_drift.py --remote` compara operações e schemas referenciados transitivamente.
Adições, remoções e mudanças nas operações habilitadas, autenticação ou Identity exigem revisão.
Mudanças fora do escopo ficam no relatório; nunca entram automaticamente nas tools.

Existe uma exceção upstream documentada em `openapi/validation-exceptions.json`: o `default: null`
de `CreatePaymentRequest.schedule` contradiz seu `oneOf`. Apenas o default daquele schema exato,
verificado por hash, é omitido da cópia em memória usada para validação. O snapshot não é alterado;
novos defeitos e mudanças no schema não recebem dispensa automática.

Para aceitar uma mudança revisada:

1. Execute `uv run python scripts/sync_openapi.py` para gerar o diff em stdout.
2. Revise o contrato; classifique novas operações explicitamente em `classifications.json`.
3. Execute `uv run python scripts/sync_openapi.py --accept` e revise snapshot, metadata e inventário.
4. Execute `make check` e envie um PR. Configure proteção de branch para exigir CI e revisão.

Nenhum workflow publica o servidor ou manipula dados financeiros. O workflow semanal pode abrir
ou comentar uma issue de drift no repositório onde for habilitado. A proteção
de branch deve ser configurada pelo mantenedor conforme o fluxo de contribuição.

O CI executa Gitleaks 8.30.1 sobre o histórico Git completo, com binário fixado por SHA-256,
sem allowlists adicionais. Fixtures e chaves criptográficas de teste são geradas sinteticamente;
o smoke HTTP não usa token nem acessa a Pluggy.
Antes de publicar, também é necessário escanear os arquivos selecionados para o commit.
