# Inventário de endpoints da Pluggy

Gerado por `scripts/sync_openapi.py`; novas operações não habilitam tools.

Fonte: https://api.pluggy.ai/oas3.json · OpenAPI 3.1.0 · 86 operações.
SHA-256: `2a54e8f84f17b8e26739799bb73f32bb8d5d0a98ec3ae4c0ec977b8c55aef422`

| Método e caminho | operationId | Risco | MCP |
|---|---|---|---|
| `DELETE /categories/rules/{id}` | `client-category-rules-delete` | R3 | excluded |
| `DELETE /items/{id}` | `items-delete` | R3 | excluded |
| `DELETE /payments/customers/{id}` | `payment-customer-delete` | R4 | excluded |
| `DELETE /payments/recipients/{id}` | `payment-recipient-delete` | R4 | excluded |
| `DELETE /payments/requests/{id}` | `payment-request-delete` | R4 | excluded |
| `DELETE /webhooks/{id}` | `webhooks-delete` | R3 | excluded |
| `GET /accounts` | `accounts-list` | R1 | enabled |
| `GET /accounts/{id}` | `accounts-retrieve` | R1 | enabled |
| `GET /accounts/{id}/balance` | `account-balance-get` | R1 | enabled |
| `GET /accounts/{id}/statements` | `account-statements-list` | R1 | enabled |
| `GET /bills` | `bills-list` | R1 | enabled |
| `GET /bills/{id}` | `bills-retrieve` | R1 | enabled |
| `GET /boletos/{id}` | `boleto-get` | R4 | excluded |
| `GET /categories` | `categories-list` | R0 | excluded |
| `GET /categories/rules` | `client-category-rules-list` | R3 | excluded |
| `GET /categories/{id}` | `categories-retrieve` | R0 | excluded |
| `GET /connectors` | `connectors-list` | R0 | excluded |
| `GET /connectors/{id}` | `connector-retrieve` | R0 | excluded |
| `GET /consents` | `consents-list` | R2 | excluded |
| `GET /consents/{id}` | `consent-retrieve` | R2 | excluded |
| `GET /identity` | `identity-find-by-item` | R2 | optional |
| `GET /identity/{id}` | `identity-retrieve` | R2 | optional |
| `GET /investments` | `investments-list` | R1 | enabled |
| `GET /investments/{id}` | `investments-retrieve` | R1 | enabled |
| `GET /investments/{id}/transactions` | `investment-transactions-list` | R1 | enabled |
| `GET /items/{id}` | `items-retrieve` | R1 | enabled |
| `GET /items/{id}/resources` | `items-resources` | R1 | excluded |
| `GET /items/{id}/scr` | `items-retrieve-scr` | R2 | excluded |
| `GET /loans` | `loans-list` | R1 | excluded |
| `GET /loans/{id}` | `loans-retrieve` | R1 | excluded |
| `GET /merchants` | `merchants-get-by-cnpj` | R0 | excluded |
| `GET /payments/customers` | `payment-customers-list` | R4 | excluded |
| `GET /payments/customers/{id}` | `payment-customer-retrieve` | R4 | excluded |
| `GET /payments/intents` | `payment-intents-list` | R4 | excluded |
| `GET /payments/intents/{id}` | `payment-intent-retrieve` | R4 | excluded |
| `GET /payments/recipients` | `payment-recipients-list` | R4 | excluded |
| `GET /payments/recipients/institutions` | `payment-recipients-institution-list` | R4 | excluded |
| `GET /payments/recipients/institutions/{id}` | `payment-recipient-institutions-retrieve` | R4 | excluded |
| `GET /payments/recipients/{id}` | `payment-recipient-retrieve` | R4 | excluded |
| `GET /payments/requests` | `payment-requests-list` | R4 | excluded |
| `GET /payments/requests/{id}` | `payment-request-retrieve` | R4 | excluded |
| `GET /payments/requests/{id}/automatic-pix/schedules` | `payment-request-get-automatic-pix-schedules` | R4 | excluded |
| `GET /payments/requests/{id}/schedules` | `payment-schedules-list` | R4 | excluded |
| `GET /payments/requests/{requestId}/automatic-pix/schedules/{paymentId}` | `payment-request-get-automatic-pix-schedule` | R4 | excluded |
| `GET /smart-transfers/payments/{id}` | `smart-transfer-paymentretrieve` | R4 | excluded |
| `GET /smart-transfers/preauthorizations` | `smart-tranfers-preauthorizations-list` | R4 | excluded |
| `GET /smart-transfers/preauthorizations/{id}` | `smart-transfer-preauthorization-retrieve` | R4 | excluded |
| `GET /smart-transfers/preauthorizations/{id}/payments` | `smart-transfer-preauthorization-payments-list` | R4 | excluded |
| `GET /transactions` | `transactions-list` | R1 | excluded |
| `GET /transactions/{id}` | `transactions-retrieve` | R1 | enabled |
| `GET /v2/items` | `items-list-by-cursor` | R2 | excluded |
| `GET /v2/transactions` | `transactions-list-by-cursor` | R1 | enabled |
| `GET /webhooks` | `webhooks-list` | R3 | excluded |
| `GET /webhooks/{id}` | `webhooks-retrieve` | R3 | excluded |
| `PATCH /items/{id}` | `items-update` | R3 | enabled |
| `PATCH /items/{id}/disable-auto-sync` | `items-disable-autosync` | R3 | excluded |
| `PATCH /payments/customers/{id}` | `payment-customer-update` | R4 | excluded |
| `PATCH /payments/recipients/{id}` | `payment-recipient-update` | R4 | excluded |
| `PATCH /payments/requests/{id}` | `payment-request-update` | R4 | excluded |
| `PATCH /transactions/{id}` | `transactions-Update` | R3 | excluded |
| `PATCH /webhooks/{id}` | `webhooks-update` | R3 | excluded |
| `POST /auth` | `auth-create` | R3 | internal |
| `POST /boleto-connections` | `boleto-connection-create` | R4 | excluded |
| `POST /boleto-connections/from-item` | `boleto-connection-create-from-item` | R4 | excluded |
| `POST /boletos` | `boleto-create` | R4 | excluded |
| `POST /boletos/{id}/cancel` | `boleto-cancel` | R4 | excluded |
| `POST /categories/rules` | `client-category-rules-create` | R3 | excluded |
| `POST /connect_token` | `connect-token-create` | R3 | excluded |
| `POST /connectors/{id}/validate` | `connectors-validate` | R3 | excluded |
| `POST /items` | `items-create` | R3 | excluded |
| `POST /items/{id}/mfa` | `items-send-mfa` | R3 | excluded |
| `POST /payments/customers` | `payment-customer-create` | R4 | excluded |
| `POST /payments/intents` | `payment-intent-create` | R4 | excluded |
| `POST /payments/recipients` | `payment-recipient-create` | R4 | excluded |
| `POST /payments/requests` | `payment-request-create` | R4 | excluded |
| `POST /payments/requests/automatic-pix` | `payment-request-create-automatic-pix` | R4 | excluded |
| `POST /payments/requests/pix-qr` | `payment-request-create-pix-qr` | R4 | excluded |
| `POST /payments/requests/{id}/automatic-pix/cancel` | `payment-request-cancel-automatic-pix-consent` | R4 | excluded |
| `POST /payments/requests/{id}/automatic-pix/schedule` | `payment-request-create-automatic-pix-schedule` | R4 | excluded |
| `POST /payments/requests/{id}/automatic-pix/schedules/{scheduleId}/cancel` | `cancel-automatic-pix-schedule` | R4 | excluded |
| `POST /payments/requests/{id}/automatic-pix/schedules/{scheduleId}/retry` | `retry-automatic-pix-schedule` | R4 | excluded |
| `POST /payments/requests/{id}/schedules/cancel` | `payment-schedules-cancel` | R4 | excluded |
| `POST /payments/requests/{id}/schedules/{scheduleId}/cancel` | `payment-schedules-cancel-specific` | R4 | excluded |
| `POST /smart-transfers/payments` | `smart-transfer-payment-create` | R4 | excluded |
| `POST /smart-transfers/preauthorizations` | `smart-transfer-preauthorization-create` | R4 | excluded |
| `POST /webhooks` | `webhooks-create` | R3 | excluded |

`enabled`: consultas e sincronização explícita de Item; `optional`: Identity não implementada;
`internal`: autenticação exclusivamente interna; `excluded`: fora do MCP.
R0: pública; R1: financeira; R2: altamente sensível; R3: administrativa; R4: pagamentos.
