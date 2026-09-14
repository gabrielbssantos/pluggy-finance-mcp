# Regras de cálculo — versão 1.0.0

Todas as agregações operam exclusivamente sobre recursos do Item configurado. Não convertem
moedas. Totais são calculados com `Decimal` e retornados como strings decimais, sem arredondamento
contábil implícito. Os dados brutos seguem como números JSON.

## Gastos e categorias

O mês padrão é o atual em `America/Sao_Paulo`. Datas de lançamento UTC são convertidas para
esse fuso; filtros upstream incluem uma margem de data, seguida de filtragem local exata.
Um intervalo explícito exige início e fim, inclusivos, e não pode ser combinado com `month`.

As regras versionadas estão em `tools/classification.py` no pacote. Elas usam exclusivamente
`type`, `status`, categoria original, `operationType` e, quando disponível, igualdade de documentos
estruturados de pagador e recebedor. Documentos pessoais são usados apenas em memória e removidos
das respostas. Descrições de transações não participam da classificação.

- Despesas efetivadas entram em `gross_expenses`; créditos identificados como `ESTORNO` entram
  em `refunds`, reduzindo `net_expenses` no período em que foram lançados.
- A parcela lançada entra pelo seu próprio `amount`; `totalAmount` da compra não é somado.
- Pagamentos de fatura, transferências próprias e aplicações identificadas ficam em `excluded`.
- Pendências não entram nos gastos efetivados. Movimentos sem evidência suficiente aparecem em
  `ambiguous`, com aviso explícito, fora do total.
- Compras com direção `DEBIT` no cartão são despesas, exceto exclusões e ambiguidades estruturadas.
  Débitos bancários exigem categoria de despesa reconhecida ou tipo de tarifa. Isso pode produzir
  um total conservador quando a categorização da Pluggy estiver ausente ou não reconhecida.
- `TRANSFERENCIA_MESMA_INSTITUICAO` não prova que o destinatário é o próprio usuário. PIX/TED/DOC
  só é transferência própria quando os documentos estruturados coincidem, ou a categoria o afirma.
- Créditos sem indicação de estorno ficam separados; o servidor não presume que todo crédito é reembolso.
- Categorias mantêm os nomes da Pluggy. Estornos sem categoria ficam em `Uncategorized`;
  não são atribuídos por semelhança a uma compra anterior.

Deduplicação usa somente IDs, dentro de cada tipo de recurso. IDs diferentes com o mesmo valor e
texto continuam sendo registros diferentes. Possíveis duplicações entre fontes não são adivinhadas.

## Saldos, carteira, faturas e patrimônio

`get_total_balance` soma saldos bancários por moeda e tipo; cartões ficam separados. O schema de
Account do snapshot não oferece instituição de origem por conta: o grupo usa `unknown` e avisa
`INSTITUTION_UNAVAILABLE`, sem inferir instituição pelo nome da conta ou pelo conector agregador.

A carteira inclui `balance` apenas de posições `ACTIVE`. Posições pendentes, resgatadas ou com
status ausente ficam visíveis entre as excluídas. Saldos ausentes geram aviso, nunca posição zero.
Instituição de investimentos usa o campo estruturado `institution.name` quando disponível.

O resumo de cartões apresenta faturas e pagamentos individualmente. Faturas históricas não são
somadas como obrigação atual. O patrimônio usa o saldo bancário, saldos de investimentos ativos
e o saldo atual de cartões; não inclui limite de crédito nem desconta suas faturas novamente.

A estimativa patrimonial é sempre parcial: não inclui empréstimos, ativos externos ou obrigações
não fornecidas pelos produtos permitidos. Contas com investimentos automáticos podem se sobrepor
à carteira; os componentes e avisos expõem essa limitação. Um saldo bancário negativo já reduz
os ativos líquidos e não é descontado duas vezes como cheque especial.

## Cobertura e limites

Cada chamada permite no máximo 10 páginas, 2.000 registros de listagens e 45 segundos, incluindo
autenticação, retentativas e verificação de vínculo. Páginas de contas e investimentos também
consomem o orçamento. A contagem de registros inclui duplicatas recebidas antes de deduplicação.

Uma página inteira que excederia o orçamento de registros é omitida, com
`RECORD_LIMIT_WHOLE_PAGE_OMITTED`; não se avança cursor silenciosamente sobre registros descartados.
Resultados já coletados são preservados em timeout, limite ou indisponibilidade upstream.
Erros de autorização ou vínculo descartam o resultado inteiro. Não há cache persistente ou retomada
oculta entre chamadas; use as tools básicas para percorrer um histórico maior.

`meta` informa `period`, `timezone`, `pages_consulted`, `records_consulted`, `completed_sources`,
`source_timestamps`, `fetched_at`, `rules_version` e `complete`. `complete=false` também pode indicar
lacunas de classificação ou metadados; consulte `warnings` para distinguir a causa.
Ausência completa de dados retorna listas vazias e aviso, não um patrimônio ou gasto igual a zero.

No patrimônio, componentes ausentes ou cuja coleta foi interrompida ficam `null`, e a estimativa
numérica fica `null` quando depende deles. Os registros disponíveis continuam na resposta.
O saldo de cartão pode não incluir dívida de faturas anteriores; saldo em moeda estrangeira
não é convertido nem somado sem moeda/taxa comprovadas. Esses casos geram avisos específicos.
Referência de interpretação: [saldos na Pluggy](https://docs.pluggy.ai/docs/accounts).
