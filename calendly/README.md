# Calendly

Plataforma de agendamento. A API v2 é REST/JSON e cobre usuários e organização, tipos de evento, disponibilidade, eventos agendados, convidados, formulários de roteamento e webhooks. Primeiro app do repositório com autenticação **`TOKEN`** (Bearer), fechando esse padrão da fila do playbook.

- Documentação: https://developer.calendly.com/api-docs
- Autenticação: `TOKEN` — Personal Access Token no header `Authorization: Bearer <token>`
- Base URL: `https://api.calendly.com`

| Ambiente | Base URL |
|---|---|
| Produção | `https://api.calendly.com` |

Não há sandbox separado: a API opera sobre a conta real. Os GETs (usuário atual, tipos de evento, eventos agendados) são seguros para validar; as operações de escrita (criar convidado, cancelar evento, criar webhook) têm efeito real.

## Obter o token (Personal Access Token)

O Calendly v2 aceita **Personal Access Token** (uso interno/privado) ou **OAuth 2.1** (apps que agem em nome de terceiros). Para cadastro no iPaaS, o PAT é o caminho direto — mapeia para o auth model `TOKEN`.

1. Entre no [developer.calendly.com](https://developer.calendly.com) e gere um Personal Access Token (Integrations → API & webhooks → Personal access tokens, na conta Calendly).
2. O token vai no header `Authorization: Bearer <token>` — o auth model `TOKEN` do iPaaS injeta isso automaticamente.

Não versione o token neste repositório. O `ipaas.json` descreve apenas o formato da autenticação. **Lembrar de rotacionar** o token depois da validação.

## Serviços (recorte por domínio)

A API v2 tem 35 operações. Agrupadas em 4 serviços de negócio:

| Serviço | Operações | Domínios | Spec |
|---|---|---|---|
| `Usuários e Organização` | 13 | Users, Organizations, Groups, Activity Log, Data Compliance | `openapi-usuarios-organizacao.ipaas.json` |
| `Agendamentos` | 6 | Scheduled Events, Invitees | `openapi-agendamentos.ipaas.json` |
| `Tipos de Evento e Disponibilidade` | 8 | Event Types, Availability, Shares | `openapi-tipos-evento-disponibilidade.ipaas.json` |
| `Roteamento e Webhooks` | 8 | Routing Forms, Webhook Subscriptions | `openapi-roteamento-webhooks.ipaas.json` |

URLs de importação:

```
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/calendly/openapi-usuarios-organizacao.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/calendly/openapi-agendamentos.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/calendly/openapi-tipos-evento-disponibilidade.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/calendly/openapi-roteamento-webhooks.ipaas.json
```

## Cadastro no iPaaS

### 1. Aplicativo

| Campo | Valor |
|---|---|
| Nome | `Calendly` |
| Descrição | Plataforma de agendamento: usuários e organização, tipos de evento e disponibilidade, eventos agendados e convidados, formulários de roteamento e webhooks. |

### 2. Ambiente

| Campo | Valor |
|---|---|
| Nome | `Produção` |
| Tipo | `REST` |
| Base path | `https://api.calendly.com` |
| Autenticação | `TOKEN` |

Os paths das specs são relativos (`/users/me`, `/scheduled_events`), sem prefixo de versão — o host base já resolve.

### 3. Conta

Obrigatória — sem ela as chamadas retornam 401.

| Campo | Valor |
|---|---|
| Nome | `Produção` |
| Tipo de autenticação | `TOKEN` |
| Token | seu Personal Access Token |

O auth model `TOKEN` tem uma única chave `token` (`config.outputSchema.token`), injetada como `Authorization: Bearer <token>`.

### 4. Serviços e importação

Quatro serviços, um por grupo de domínio (ver tabela acima). Cada serviço importa a URL raw do `.ipaas.json` correspondente.

## Como as specs foram geradas

A doc oficial do Calendly migrou para o ReadMe (developer.calendly.com), uma SPA sem um arquivo OpenAPI público baixável. A fonte usada foi o espelho **apis.io** (`github.com/api-evangelist/calendly`), que publica a API v2 recortada por domínio em OpenAPI 3.1.0, com `bearerAuth`, `tags` e `summary` em toda operação. É espelho de terceiro (não a spec oficial do fornecedor), derivado da API real.

Fluxo (script `_build.py` neste diretório):

1. Download das 12 specs por domínio de `github.com/api-evangelist/calendly/openapi/`.
2. Agrupamento em 4 serviços de negócio, mesclando `paths` + `components` de cada grupo (sem colisão de componentes entre domínios).
3. Rebaixamento **OpenAPI 3.1.0 → 3.0.3** (o importador do iPaaS só foi validado com OAS 3.0). O saneamento trata: `type` como lista com `"null"` → `type` escalar + `nullable`; `const` → `enum`; `examples` plural em schema removido; `exclusiveMinimum`/`Maximum` numéricos → booleanos.
4. `python3 tools/dereference.py calendly` gerou os `*.ipaas.json`.

Resultado: 35 operações, 0 `$ref` restante, todas com `tags` e `summary`, apenas `bearerAuth` em `securitySchemes`.

O `bearerAuth` é `type: http`, `scheme: bearer` — fica **no header**, então não cai na armadilha do importador com `securityScheme` em `query` (seção 4 do playbook).

## Validação

**Validado em diagrama** (`Valida Calendly`, projeto `Validação apps`). Conta criada com Personal Access Token; 3 steps de leitura em série, os três confirmados na rastreabilidade:

| Step | Operação | Serviço |
|---|---|---|
| 1 | `GET /users/me` | Usuários e Organização |
| 2 | `GET /event_types?user={uri}` | Tipos de Evento e Disponibilidade |
| 3 | `GET /scheduled_events?user={uri}` | Agendamentos |

Os steps 2 e 3 exigem `user` como parâmetro obrigatório, encadeado do step 1 com `{{{id1.resource.uri}}}` em `configurations.inQuery`. O `uri` do usuário vem em `resource.uri` do `GET /users/me` (a organização em `resource.current_organization`).

O Personal Access Token usado foi compartilhado em chat e **deve ser rotacionado**. Se a execução passar a dar 401, é provável que tenha sido trocado — gere um novo e atualize a conta com `PUT /ipaas/api/v3/accounts/{id}` (com `active: true`, senão a conta é desativada).

## Observações

Os schemas vêm do espelho apis.io. Os retornos de `GET /users/me`, `GET /event_types` e `GET /scheduled_events` foram confirmados na execução do diagrama; os demais não foram conferidos contra respostas reais. O Calendly usa **URIs** (não IDs simples) para referenciar recursos: a maioria dos endpoints de listagem exige `user` ou `organization` como URI em query. As respostas seguem o padrão `{ "resource": {...} }` (item único) ou `{ "collection": [...], "pagination": {...} }` (listas).

Domínios da API v2 não cobertos por não terem spec no espelho ou serem de nicho: nenhum relevante ficou de fora — os 12 domínios publicados foram todos incluídos nos 4 serviços.
