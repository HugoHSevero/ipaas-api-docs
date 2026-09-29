# Playbook - Montagem de diagramas no TOTVS iPaaS via API

Referência para um agente de IA montar, publicar, executar e depurar diagramas (integrações) do TOTVS iPaaS pela API, sem arrastar caixas no builder.

O foco é o **diagrama**. O documento traz também o mínimo para garantir os pré-requisitos dos steps (ambiente e conta, seção 3). O cadastro de um aplicativo novo (app, serviço, importação de Swagger) está fora do escopo.

Legenda de confiança, usada em todo o documento:

- **[V]** verificado: salvo, publicado e executado com sucesso, com rastreabilidade conferida.
- **[P]** publicado sem erro, mas não executado.
- **[S]** só levantado do schema do componente ou do bundle do front. Trate como hipótese.

Levantamento feito em 28/09/2026 no tenant `iPaaS Gateway` (produção), com os diagramas `Valida WhatsApp` e `ZZ Playbook - condicoes (teste)`.

---

## 1. Regras de ouro

1. **Diagrama novo só nasce pela interface.** `POST /v2/integrations/sketch/project/{projectId}` existe, mas responde `403 Could not verify the provided CSRF token` fora do front. Crie pela UI (seção 3.5) e faça todo o resto por API.
2. **O `integrationId` é estável; o `diagramId` muda a cada save.** Leia sempre com `lastVersion=true`. A URL do builder (`/builder/{id}`) usa o **`diagramId`**, não o `integrationId`.
3. **Publish com erro mantém a versão anterior no ar.** Um `500 FLUIG_CONNECTOR_ENGINE_0011` não derruba nada, mas a execução seguinte roda a versão **antiga**. Sempre confira o status do publish antes de testar.
4. **O tipo do gatilho define o que é permitido.** Webhook síncrono **não aceita** Splitter, Global error nem Throw Exception. Webhook assíncrono **não aceita** Resposta síncrona (seção 5).
5. **Pré-requisitos antes do diagrama:** app, serviço com recursos importados, ambiente e conta ativa (se o ambiente tiver auth). Confira por GET. Ambiente e conta faltando: cadastre (seções 3.3 e 3.4). App, serviço ou recurso faltando: pare e avise o usuário, porque é cadastro de aplicativo.
6. **Valide executando e lendo os steps**, não só pelo `200` do publish. A rastreabilidade mostra até a expressão de cada condição já avaliada (seção 12).
7. **Não altere o que é de outro fluxo.** Diagramas `Valida *` são de validação dos apps; auth models, utilitários e `originalComponentId` são IDs globais da plataforma (seção 13).

---

## 2. Sessão e autenticação

Tudo roda de dentro de uma aba autenticada em `https://ipaas.totvs.app`, com o JWT do cookie como Bearer. Peça ao usuário para logar; não automatize SSO/MFA.

```js
const t = document.cookie.match(/(?:^|;\s*)jwt\.token=([^;]+)/)[1];
const H = { authorization: 'Bearer ' + t, accept: 'application/json', 'content-type': 'application/json' };
const B = 'https://api-ipaas.totvs.app/ipaas/api';
```

Valide com uma chamada real (`GET /v2/auth-models?page=1&pageSize=1` → 200). O token vale cerca de 48 horas; 401 no meio da sessão é ele — peça novo login.

O builder recarrega a página em alguns eventos (publicar, trocar de versão) e **apaga variáveis globais** (`window.x`). Para scripts longos, guarde o código auxiliar em `localStorage` e recrie a cada chamada, ou refaça o `fetch` do flow a partir da API em toda chamada.

O tenant usado é **produção** (`iPaaS Gateway`, nome no cabeçalho da interface). Confirme com o usuário antes de criar ou publicar.

---

## 3. Pré-requisitos e criação do diagrama

### 3.1 O que cada step REST precisa

Um step de aplicativo referencia quatro cadastros. Levante todos por GET antes de montar o flow:

| Dado do step | De onde vem |
|---|---|
| `componentId` (app) | `GET /v3/applications?page=1&pageSize=9999` → campo `componentId` (não `id`) |
| `serviceId` / `applicationService` | `GET /v3/application-services?applicationId={app}` |
| `componentResourceId` (operação) | `GET /v3/rest-resources?serviceId={id}&fields=id&fields=name&page=1&pageSize=9999`. Nome no formato `{MÉTODO} - {tag} - {path} - {summary}` |
| campos da operação | `GET /v3/resources?serviceId={id}&id={resourceId}&expand=properties&expand=model` → `inputSchema` (`inPath`, `inQuery`, `inHeader`) e `responseBody` |
| `environmentId` | `GET /v2/environments/?applicationId={app}&expand=authModels&expand=accounts&expand=environmentsChild` |
| `accountId` | mesma chamada (`accounts`) ou `GET /v3/accounts?componentId={app}&page=1&pageSize=100`. Precisa de `active: true` |

App com `isCustom: false` é do catálogo TOTVS; use, mas não altere.

**Ambiente custom** (baseURL com placeholder, ex. `https://{environment}.asaas.com`): no step use o **ambiente filho** (em `environmentsChild`), que tem a URL concreta. A conta vinculada ao pai vale para os filhos.

**Ambiente `NO_AUTH`** dispensa conta e `accountId`.

### 3.2 Modelos de autenticação (IDs globais)

`GET /v2/auth-models?page=1&pageSize=999`.

| Tipo | ID | `config.outputSchema` da conta (\* = obrigatório) |
|---|---|---|
| `NO_AUTH` | `d6a952f5-7ce3-44e4-af8e-8697c3ef4b37` | — |
| `BASIC` | `4a4d0fa1-2933-438d-a6ac-36432bc2cf42` | `username*`, `password*` |
| `TOKEN` | `3ce568bb-e05a-4186-b650-9faa63c46041` | `token*` |
| `API_KEY` | `e90e6f18-c1bb-4170-9d10-5e45be5314c6` | `addTo*` (`header`/`query`), `keys` (lista `key`/`value`) |
| `OAUTH1` | `e5e4bb18-0f2b-4e3e-be33-412fab6a6b2b` | `consumerKey*`, `consumerSecret*`, `accessToken*`, `tokenSecret*` |
| `OAUTH2_CLIENT` | `45ff3eb3-111f-4a35-b665-579519a1c87e` | `accessTokenURL*`, `client_id*`, `client_secret*`, `clientAuth*`, `scope`, `grant_type` |
| `OAUTH2_PASSWORD` | `9afef6ed-83f3-4293-ba3a-37bf6df6d8cf` | `accessTokenURL*`, `username*`, `password*`, `client_id*`, `client_secret*`, `clientAuth*` |
| `OAUTH2_CODE` | `158e40cb-53b4-4381-95a7-4857b7156019` | `authURL*`, `accessTokenURL*`, `code*`, `client_id*`, `client_secret*`, `clientAuth*` |
| `NTLM` | `0d5bba8e-d15e-4cb6-bfd4-7904fbb8cb61` | `username*`, `password*`, `domain`, `workstation` |
| `AWS_SIGNATURE` | `240ecfed-628f-436b-be67-5e8984bfcf39` | `accessKey*`, `secretKey*`, `awsRegion*`, `serviceName*`, `sessionToken` |

`clientAuth`: `header` ou `body`. OAuth2 authorization code exige interação de navegador para obter o `code`: peça ao usuário para cadastrar essa conta pela UI.

### 3.3 Criar o ambiente, se não existir

`POST /v2/environments` → 200

```json
{
  "name": "Produção",
  "type": "REST",
  "baseURL": "https://api.exemplo.com/v1",
  "applicationId": "<componentId do app>",
  "authModelIds": ["<id do auth model>"],
  "active": true
}
```

- O vínculo é **`authModelIds`** (lista de ids). Enviar `authModels` com objetos é aceito e **não vincula nada**.
- `baseURL` sem barra final e sem repetir prefixo que já está nos paths dos recursos (ex.: `/v3`).
- A resposta do POST mostra `active: false`; um GET em seguida mostra `true`. Não "corrija".
- Editar: `PUT /v2/environments/{id}` com o corpo completo. Ambiente custom com filhos: crie pela UI.

### 3.4 Criar a conta, se não existir

`POST /v3/accounts` → 201

```json
{
  "authType": "API_KEY",
  "modelId": "e90e6f18-c1bb-4170-9d10-5e45be5314c6",
  "componentId": "<componentId do app>",
  "environmentId": "<id do ambiente>",
  "name": "Produção",
  "config": { "outputSchema": { "addTo": "header", "keys": [{ "key": "api-key", "value": "<credencial>" }] } }
}
```

Para `TOKEN`: `"authType": "TOKEN"`, `"modelId": "3ce568bb-e05a-4186-b650-9faa63c46041"`, `"config": { "outputSchema": { "token": "<token>" } }`.

- `environmentId` é **string**. `environments: [{id}]` (formato da leitura) dá `500 Name is null`.
- `authType` e `modelId` são os dois obrigatórios e se referem ao mesmo auth model.
- **Peça a credencial ao usuário.** Não leia de arquivo, não grave em arquivo versionado, não repita o valor na resposta.
- Não existe `GET /v3/accounts/{id}` (500). Leia pela listagem ou pelo `expand=accounts` do ambiente.
- **`PUT /v3/accounts/{id}` sem `active: true` desativa a conta** (e a listagem confirma `false`). Mande sempre o corpo completo com `"active": true` e confira depois.
- `GET /v3/accounts/testAccount/{id}` não é confiável para validar credencial. Valide executando o diagrama.

### 3.5 Criar o diagrama (UI) e obter os IDs

```
Projetos → <projeto> → Criar diagrama → Em branco → Nome + Descrição → Criar diagrama
```

O builder abre em `/builder/{diagramId}`. Pegue o `integrationId`:

```
GET /v3/integrations?diagramId={diagramId}&fieldsReturn=id,diagramId,name,status,flow
```

O diagrama nasce `IN_SKETCH` com `flow: { aync: false, functions: {}, activities: {} }` (o typo `aync` é do backend; ignore). Projeto de validação usado: `Validação apps` (`b977af3c-db40-4586-bb47-80c4b3b45d89`).

---

## 4. Estrutura do flow

```json
{
  "async": false,
  "start": "<id do gatilho>",
  "functions": { "<idFn>": { ... } },
  "activities": { "<idStep>": { ... }, "<origem>#<destino>": { ...condição... } },
  "globalErrorFlow": { "start": "global-error-start", "activities": { ... } }
}
```

`async` fica `false` mesmo em diagrama com Webhook assíncrono (é o que o front grava). O que define síncrono/assíncrono é o **tipo do gatilho**.

### 4.1 Campos comuns de um step

| Campo | Uso |
|---|---|
| `id` | chave do step; usado nas referências `{{{id...}}}` |
| `type` | tipo do motor (tabela 6.1) |
| `name` | nome do componente (ex.: `JavaScript`) |
| `label` | texto da caixa; o front sobrescreve com `configurations.name` |
| `positions` | `{ top: "9000px", left: "9280px" }`; o canvas começa perto de `9000px` |
| `originalComponentId` | id do componente na plataforma (tabela 6.1) |
| `isDropped`, `hidden` | `true` / `false`, como o front grava |
| `configurations` | parâmetros do componente |
| `connections.next` / `previous` | ids dos vizinhos (ou do nó de condição `A#B`) |
| `connections.finalConnections` | desenho das setas (4.3) |

### 4.2 Convenção de IDs

O front gera ids assim; siga o mesmo padrão para o diagrama abrir corretamente na interface:

| Step | ID |
|---|---|
| Webhook síncrono | `webhook-sync-trigger` |
| Webhook assíncrono | `webhook-hook-trigger` |
| App REST | `id1`, `id2`, ... |
| Demais componentes | `id-<sufixo><n>`: `id-javascript1`, `id-data-storage2`, `id-throw-exception1`, `id-splitter1`, `id-synchronous-webhook-response1`, `id-jolt1`, `id-mail1`, `id-converter1`, `id-generator1`, `id-ftp1`, `id-xslt1`, `id-newjdbc1`, `id-diagram-caller1`, `id-smartlink-sender1`, `id-message-broker-send1` |
| Global error (só um por diagrama) | `id-global-error` |
| Início do subfluxo do splitter | `splitter-start<n>` (mesmo `n` do `id-splitter<n>`) |
| Início do global error | `global-error-start` |
| Condição / alternativa | `<idOrigem>#<idDestino>` |
| Função | livre; o front usa ids próprios (`id-function1` funcionou) |

A numeração é por tipo, não global: `id-javascript1` e `id-data-storage1` podem coexistir.

### 4.3 Setas (`finalConnections`)

`next`/`previous` bastam para **executar**. Sem `finalConnections`, o diagrama executa mas abre no builder **sem setas** [V]. Preencha no step de **origem**:

```json
"finalConnections": [{
  "connectionId": "id1#id2",
  "connectionPath": "M {sx} {sy}\n    L {sx-32} {sy} L {sx} {sy}\n    L {mx} {sy} L {mx} {ey}\n    T {ex} {ey}"
}]
```

`mx = (sx+ex)/2`. Offsets a partir de `positions`:

| Tipo | Saída | Entrada |
|---|---|---|
| Gatilhos (círculo) | `left+66`, `top+32` | — |
| Caixas (REST, JS, etc.) | `left+79`, `top+45` | `left-9`, `top+45` |
| Resposta síncrona | — | `left-8`, `top+32` |

Com condição, o `connectionId` continua `origem#destino` (o mesmo id do nó de condição) [V].

---

## 5. Gatilhos e o que cada um permite

| Gatilho | `type` / id | Resposta síncrona | Splitter | Global error | Throw Exception |
|---|---|---|---|---|---|
| Webhook síncrono | `WEBHOOK_SYNC` / `webhook-sync-trigger` | sim, obrigatória | **não** | **não** | **não** |
| Webhook | `WEBHOOK` / `webhook-hook-trigger` | **não** | sim | sim | sim |
| Timer | `QUARTZ` | [S] | [S] | [S] | [S] |
| SmartLink Hook, Message Broker Hook | `SMARTLINK_HOOK`, `MESSAGE_BROKER_HOOK` | [S] | [S] | [S] | [S] |

A matriz de Webhook síncrono x assíncrono foi conferida na paleta do builder (componentes esmaecidos) e pelo publish: Throw Exception em diagrama síncrono resulta em `500 FLUIG_CONNECTOR_ENGINE_0011` [V].

Gatilho não tem `configurations` relevantes: `{}`. O payload recebido fica em `{{{<gatilho>.inBody...}}}` e os headers em `{{{<gatilho>.inHeader...}}}`.

**Escolha do gatilho pelo caso de uso:**

- Precisa devolver o resultado para quem chamou → Webhook síncrono + Resposta síncrona.
- Precisa iterar lista, tratar erro globalmente ou abortar com erro de negócio → Webhook assíncrono.
- Execução agendada → Timer (configure pela UI; ver 6.3).

---

## 6. Catálogo de componentes

Catálogo completo: `GET /v3/utilities?page=1&pageSize=9999&order=name`. Formulário (schema) de cada um: `GET /v3/utility-resources?utilityId={id}&order=name&pageSize=999&allVersions=true` — use o recurso de maior `version`.

### 6.1 IDs globais (não alterar)

| Componente | `type` no flow | `originalComponentId` | Status |
|---|---|---|---|
| Webhook síncrono | `WEBHOOK_SYNC` | — (sem campo) | [V] |
| Webhook | `WEBHOOK` | — | [V] |
| Resposta síncrona | `WEBHOOK_RESPONSE` | `76c0da1d-ca69-4381-9124-d5d40d9eb106-synchronous-webhook-response` | [V] |
| App REST | `REST` | `<componentId do app>` | [V] |
| Condição | `CONDITION` | `98405216-83c8-468d-9c53-73d4694143f8` (também em `componentId`) | [V] |
| Alternativa | `OTHERWISE` | `98405216-83c8-468d-9c53-73d4694143f8` (também em `componentId`) | [V] |
| JavaScript | `JAVASCRIPT` | `78f4d43e-fae4-4849-9c01-57373eed74b4-javascript` | [V] |
| Throw Exception | `EXCEPTION` | `f5547c11-3d7d-4087-b5cc-30e1fba7f4ee-throw-exception` | [V] |
| Splitter | `SPLIT` | `1b35a577-25ae-41e3-b6ba-d7530a066b93-splitter` | [V] |
| Splitter start | `SPLIT_START` | `8f55959c-83ba-4fde-91d7-7ab6c3638822` | [V] |
| Global error | `GLOBAL_ERROR` | `98e39adf-35b6-49e6-8a3c-2de9cb370395-global-error` | [V] |
| Global error start | `GLOBAL_ERROR_START` | `f6e8b5a9-3960-437f-943d-6e32ae9195c9` | [V] |
| Function | `FUNCTION_*` (em `flow.functions`) | `componentId: c1f2d51b-c71e-45d6-b9a5-3489836c8490` | [V] |
| Data Storage | `DATA_STORAGE` | `c4f6bc3d-633f-4e12-ba01-604c3bea5e4c-data-storage` | [P] |
| E-mail | `MAIL` | `bf0992a5-708e-477e-8fcd-240d5e35d6c6-mail` | em uso em diagrama publicado do tenant |
| Converter | `CONVERTER` | `1d122d4d-20c1-41d7-9e1d-f9efcd1279c9-converter` | em uso em diagrama publicado do tenant |
| Jolt | `JOLT` | `1e9c030d-d4f4-4b3d-9818-ba36d3fe4808-jolt` | [S] |
| Diagram Caller | `DIAGRAM_CALLER` | `a95a3820-8420-409a-b880-68420ccd032e-diagram-caller` | [S] |
| Generator | `GENERATOR` | `b88804ef-b3b9-4920-8b18-c23dbf0b2ffc-generator` | [S] |
| FTP | `FTP` | `f7c4c333-6107-475c-a12f-9e976c39ba8a-ftp` | [S] |
| XSLT | `XSLT` | `8598ed63-e88b-4456-90d2-8c2423b4583c-xslt` | [S] |
| JDBC | `JDBC` | `904abb5e-f80b-42e8-b9b2-fbf60a5a23e0-newjdbc` | [S] |
| Message Broker (envio) | `MESSAGE_BROKER` | `d284a154-9817-4925-b503-876601ae7279-message-broker-send` | [S] |
| SmartLink Sender | `SMARTLINK_SENDER` | `65a85bc0-71af-46b7-b860-30797ae2e0bc-smartlink-sender` | [S] |
| Timer | `QUARTZ` | não levantado (utility `ba66d949-4a58-4414-97ed-3d0a1c07d1fd`) | [S] |

O padrão é `<utilityId>-<sufixo do id>`. Para componentes [S], confirme arrastando um na UI e lendo o flow salvo (seção 14.3) antes de gerar em lote.

**`serviceId` e `configurations.applicationService`** aparecem em JavaScript, Data Storage, E-mail e Converter gravados pelo front (valor = utilityId) e funcionam. No **Throw Exception** eles **quebraram o publish** (`ENGINE_0011`); sem eles, publicou e executou [V]. Na dúvida, grave exatamente o que o front grava.

### 6.2 Componentes verificados

#### App REST [V]

IDs levantados conforme a seção 3.1.

```json
{
  "id": "id1", "name": "<app>", "type": "REST", "label": "<rótulo>",
  "isCustom": true, "isDropped": true, "positions": { "top": "9000px", "left": "9280px" },
  "serviceId": "<serviço>", "componentId": "<app>", "originalComponentId": "<app>",
  "componentResourceId": "<recurso importado>",
  "configurations": {
    "name": "<rótulo>", "environmentId": "<ambiente>", "applicationService": "<serviço>",
    "accountId": "<conta, se o ambiente tem auth>",
    "inPath": {}, "inQuery": {}, "inHeader": {}, "inBody": {}
  },
  "connections": { "next": [], "previous": [] }
}
```

| Chave | Uso |
|---|---|
| `inPath` | parâmetros de path, com a chave igual ao nome do parâmetro do recurso: `{ "Phone-Number-ID": "123" }` |
| `inQuery` | query string: `{ "limit": "2", "fields": "name,status" }` |
| `inHeader` | headers adicionais |
| `inBody` | corpo de POST/PUT, como objeto JSON |
| `accountId` | obrigatório quando o ambiente tem autenticação; sem conta não há como autenticar o step |

- **O corpo do POST/PUT vai sempre em `inBody`**, montado à mão a partir da documentação da API. O importador do iPaaS não traz o `requestBody` para o recurso, então a interface não mostra esses campos, mas na execução vale o que estiver em `configurations`. APIs que mandam tudo em query (ex.: Trello) usam `inQuery`.
- Parâmetro de path sem valor faz a chamada falhar. Preencha todos.
- Em conta OAuth2 o front grava também `configurations.accountType` (ex.: `OAUTH2_CODE`).
- Saída: `{{{id1}}}` (payload inteiro), `{{{id1.campo}}}` ou `{{{id1.inBody.campo}}}` — as duas formas aparecem em diagramas publicados. Encadear: `"inPath": { "id": "{{{id1.id}}}" }`, `"inBody": { "customer": "{{{id1.id}}}" }` [V].
- O step fica `DONE` quando o fornecedor devolve 2xx. **`DONE` não prova efeito real**: plataformas de mensagem aceitam e descartam. Confirme na fonte quando importar.
- Cuidado com respostas grandes em fluxo síncrono: agregar tudo na resposta pesa (visto 476 KB / 38 s com 15 steps). Mantenha a resposta enxuta.

#### Resposta síncrona [V]

```json
{
  "id": "id-synchronous-webhook-response1", "name": "Resposta síncrona", "type": "WEBHOOK_RESPONSE",
  "label": "Resposta síncrona", "positions": { "top": "9013px", "left": "9680px" },
  "displayName": "backend.components.label.syncResponse",
  "originalComponentId": "76c0da1d-ca69-4381-9124-d5d40d9eb106-synchronous-webhook-response",
  "configurations": { "response": "{\"ok\": true, \"dados\": {{{id1}}}}", "status": 201 },
  "connections": { "next": [], "previous": ["id1"] }
}
```

`response` é **texto** com template. `status` define o HTTP devolvido ao chamador [V] (default 200). A resposta chega embrulhada: `{ messageId, result: <seu JSON>, status, timestamp }`.

**Sem `originalComponentId`, a rastreabilidade quebra**: o backend devolve `componentDTO: null` para o step e a tela de detalhe da mensagem fica presa em skeleton. Execuções feitas antes da correção continuam quebradas; só as novas ficam boas.

Se o texto renderizado não for JSON válido, o chamador recebe **HTTP 200** com `error: "Unexpected character..."` no corpo e o step fica `ERROR` [V]. Confira o JSON no `result`, não só o status HTTP.

#### JavaScript [V]

```json
"configurations": {
  "name": "Calcula",
  "applicationService": "78f4d43e-fae4-4849-9c01-57373eed74b4",
  "script": "const body = {{{webhook-sync-trigger.inBody}}};\nreturn { dobro: body.valor * 2 };"
}
```

O template é substituído **como texto** antes de rodar. Objetos e números entram como literais JS; **strings entram sem aspas** — ponha aspas em volta: `"{{{x.nome}}}"`. Esquecer as aspas numa string gera erro de execução (visto no Global error: `msg: {{{global-error-start.inBody.message}}}` quebrou; `"{{{...}}}"` funcionou).

Saída: `{{{id-javascript1.output}}}` e `{{{id-javascript1.output.campo}}}` [V]. `{{{id-javascript1}}}` devolve `{ "output": ... }`.

Exceção não tratada (`throw new Error(...)`) marca o step como `ERROR` e dispara o Global error [V].

#### Throw Exception [V] — só em diagrama assíncrono

```json
{
  "id": "id-throw-exception1", "name": "Throw Exception", "type": "EXCEPTION",
  "label": "Falha proposital", "hidden": false, "isDropped": true,
  "positions": { "top": "9000px", "left": "9280px" },
  "originalComponentId": "f5547c11-3d7d-4087-b5cc-30e1fba7f4ee-throw-exception",
  "configurations": { "name": "Falha proposital", "userExceptionMessage": "Erro de negocio: {{{webhook-hook-trigger.inBody.motivo}}}" },
  "connections": { "next": [], "previous": ["webhook-hook-trigger#id-throw-exception1"] }
}
```

A mensagem fica `ERROR`, com `finalComponent` = rótulo do Throw Exception e o texto renderizado no `outMessage` do step. **Não dispara o Global error** [V]: é um encerramento controlado.

#### Data Storage [P]

Chave/valor persistente do tenant, compartilhado entre diagramas.

| `storageAction` | Campos |
|---|---|
| `CREATE` | `key`*, `value` (texto JSON, até 10.000 chars), `upsert`* (bool, substitui se existir) |
| `UPDATE` | `key`*, `value`, `upsert`* (bool, cria se não existir) |
| `READ` | `key`*, `throwIfNotFound`* (bool) |
| `DELETE` | `key`*, `throwIfNotFound`* (bool) |
| `LIST` | `filter`, `pageSize`, `page` |

`key` aceita só letras e números. Saída: `inBody.key`, `value`, `found`, `items`, `page`, `size`, `totalElements`, `totalPages`. Exemplo real do tenant (diagrama `Get book`):

```json
"configurations": { "name": "Get book", "storageAction": "READ", "throwIfNotFound": true,
  "key": "{{{webhook-sync-trigger.inBody.id}}}", "applicationService": "c4f6bc3d-633f-4e12-ba01-604c3bea5e4c" }
```

Existe limite de chaves por tenant (mensagem `keyLimitExceeded`). Não use em loops de teste.

### 6.3 Componentes só levantados do schema [S]

Campos de `configurations` extraídos do formulário. `*` = obrigatório.

| Componente | Campos |
|---|---|
| E-mail | `emailAction`* = `SEND_EMAIL`: `to`*, `cc`, `cco`, `subject`*, `message`* (HTML), `attachment`; `RECEIVE_EMAIL`: `filters.folder`*, `filters.subject`, `filters.sender`, `maxResults`* (1–100), `processAttachments`, `processBody`, `readed`, `delete`. Exige `utilitySettingId` (configuração SMTP/IMAP do tenant, criada pela UI) |
| Jolt | `name`*, `input` (JSON), `spec`* (JSON). Saída `output` |
| Diagram Caller | `header` (lista `key`/`value`), `body` (JSON). Chama diagrama Webhook/Webhook síncrono do mesmo tenant. Saída `inResponse.inHeader`, `inResponse.inBody.result`, `inResponse.HttpStatus` |
| Converter | `docType`* = `CSV` \| `JSON` \| `XML` \| `BASE64`; conforme o tipo: `content`*, `delimiterType` (`COMMA`, `SEMICOLON`, `TAB`, `PIPE`, `CUSTOM`), `withHeader`, `converterDocType` (destino). Saída `result` |
| Generator | `name`*, `fileFormat`* = `JSON` \| `XML`, `fileContent`*. Saída `result` |
| XSLT | `name`*, `xml`*, `xslt`*. Saída `result` |
| FTP | `ftpAction`* = `LIST_FILES` (`ftpFolderPath`*, `fileFilter`), `DOWNLOAD_FILES` (`filePath`*, `deleteFile`), `UPLOAD_FILES` (`filePath`*, `fileContent`*, `makeDirectory`), `DELETE_FILES` (`filePath`*). Exige configuração de FTP do tenant |
| JDBC | `name`*, `driver`* = `POSTGRESQL` \| `MYSQL` \| `SQLSERVER` \| `ORACLE`, `url`*, `userName`*, `password`*, `sql`*. Saída `result` |
| Message Broker | `brokerType`* = `RABBITMQ` \| `LAVINMQ` \| `ACTIVEMQ` \| `GOOGLECLOUD` \| `KAFKA`; `message`*, e conforme o broker `exchange`/`routingKey`, `destinationName`/`destinationType`, `topicName`/`topic`, `headers`, `additionalParameters` |
| SmartLink Sender | `name`*, `type`, `eventType`* = `CLOUDEVENTS` (`context`, `cloudEventsType`* `BINARY`/`STRUCTURED`) \| `TOTVSMESSAGE` (`activityId`, `taskId`, `planItemId`, `assignee`, `roles`), `content`* |
| Timer | `frequency` = `0` uma vez, `1` diário, `2` semanal, `5` quinzenal, `3` mensal, `4` personalizado; subcampos `executionDate`, `executionTime`, `timezone` (só `America/Sao_Paulo`), `intervalType` (`0` minutos, `1` horas, `2` período), `minutesInterval` (`3`,`5`,`10`,`15`,`30`), `weekDays`, `monthDay`. A integração expõe `timerConfiguration` como expandable; **configure o Timer pela UI** |

Credenciais em JDBC/SMTP/FTP são dados sensíveis: peça ao usuário, prefira variáveis do tipo segredo e nunca grave em arquivo versionado.

---

## 7. Condições (desvios)

Condições ficam **nas linhas**, não em caixas. Cada ligação condicional vira um nó próprio em `activities` com id `origem#destino`.

### 7.1 Formato [V]

```json
"webhook-sync-trigger": {
  "connections": {
    "next": ["webhook-sync-trigger#id-synchronous-webhook-response1",
             "webhook-sync-trigger#id-synchronous-webhook-response2"],
    "previous": [],
    "finalConnections": [ /* setas com os mesmos connectionId */ ]
  }
},
"webhook-sync-trigger#id-synchronous-webhook-response1": {
  "id": "webhook-sync-trigger#id-synchronous-webhook-response1",
  "type": "CONDITION", "name": "tipo igual A", "label": "",
  "componentId": "98405216-83c8-468d-9c53-73d4694143f8",
  "originalComponentId": "98405216-83c8-468d-9c53-73d4694143f8",
  "connections": { "next": ["id-synchronous-webhook-response1"], "previous": ["webhook-sync-trigger"] },
  "configurations": {
    "conditionType": "simple",
    "conditions": [[
      { "input": "{{{webhook-sync-trigger.inBody.tipo}}}", "operation": "EQUALS", "expected": "A", "booleanOperator": "&&" }
    ]]
  }
},
"webhook-sync-trigger#id-synchronous-webhook-response2": {
  "id": "webhook-sync-trigger#id-synchronous-webhook-response2",
  "type": "OTHERWISE", "name": "senao", "label": "Otherwise",
  "componentId": "98405216-83c8-468d-9c53-73d4694143f8",
  "originalComponentId": "98405216-83c8-468d-9c53-73d4694143f8",
  "connections": { "next": ["id-synchronous-webhook-response2"], "previous": ["webhook-sync-trigger"] }
},
"id-synchronous-webhook-response1": { "connections": { "previous": ["webhook-sync-trigger#id-synchronous-webhook-response1"] } }
```

O `next` da origem e o `previous` do destino apontam para o **nó de condição**, não direto um para o outro.

### 7.2 Semântica [V]

- **Exclusiva, primeira que casar.** Quando duas condições da mesma origem são verdadeiras, só um ramo executa.
- **A ordem de avaliação não é a do array `next`.** Com `[simples, avançada, otherwise]` e as duas verdadeiras, executou o ramo da avançada. Não dependa da ordem: **escreva condições mutuamente exclusivas**.
- **Otherwise** executa só quando nenhuma condição da mesma origem casa. Precisa de pelo menos uma condição irmã.
- **Condição pode sair de qualquer step**, não só do gatilho (verificado saindo de JavaScript).

### 7.3 Condição simples

`conditions` é uma lista de **grupos**; cada grupo é uma lista de regras.

| Campo | Valores |
|---|---|
| `input` | template ou literal |
| `operation` | `EQUALS`, `NOT_EQUALS`, `LESS_THAN`, `GREATER_THAN`, `LESS_THAN_OR_EQUALS`, `GREATER_THAN_OR_EQUALS` |
| `expected` | literal ou template |
| `booleanOperator` | `&&` ou `\|\|` entre as regras do grupo (use o mesmo em todas do grupo) |
| `groupOperator` | `&&` ou `\|\|` entre grupos; **só no primeiro item do segundo grupo em diante** |
| `internalGroup` | lista de regras aninhadas, com o mesmo formato; **omita quando vazia** |

Expressões geradas, como aparecem na rastreabilidade [V]:

| `conditions` | Expressão avaliada |
|---|---|
| `[[{tipo EQUALS A}]]` | `'A' == 'A'` |
| `[[{tipo EQUALS A, bool ‖}, {tipo EQUALS C, bool ‖}]]` | `'C' == 'A' \|\| 'C' == 'C'` |
| `[[{tipo = A}, {valor < 100}], [{tipo = C, groupOperator ‖}]]` | `('C' == 'A' && 500 < 100) \|\| ('C' == 'C')` |
| `[[{tipo = A, internalGroup: [{valor < 100, bool ‖}, {valor > 1000, bool ‖}]}]]` | `'A' == 'A' && (2000 < 100 \|\| 2000 > 1000)` |

Armadilhas [V]:

- **`internalGroup: []` gera `&& ()`** e a expressão fica inválida. Com o operador de grupo no lugar errado sai `( || (...)...)`. Nos dois casos, o resultado reportado foi `false` e mesmo assim **o ramo executou**. Não mande `internalGroup` vazio e ponha `groupOperator` só onde a tabela indica.
- **Tudo vira string na comparação.** `true` do payload vira `'true'`: use `expected: "true"`. Números comparam como número (`500 < 100`).

### 7.4 Condição avançada

```json
"configurations": { "conditionType": "advanced", "advanced": "{{{webhook-sync-trigger.inBody.valor}}} > 10" }
```

Expressão JavaScript com `&&`/`||`. O template entra como texto: números funcionam direto (`50 > 10`); strings precisam de aspas na expressão (`{{{x.tipo}}} == 'A'`, o valor já chega com aspas simples) [V].

- **Booleano não casa com `== true`.** `{{{x.falhar}}} == true` com `falhar: true` resultou em falso e foi para o otherwise [V]. Use condição simples com `expected: "true"`, ou `== 'true'`.
- **Efeito colateral nos steps seguintes** [V]: quando uma condição **avançada** é avaliada (no ramo seguido ou num ramo irmão da mesma origem), campos string usados em condições passam a interpolar **com aspas simples** nos steps seguintes (`"q":"{{{...tipo}}}"` virou `"'A'"`). Com só condições simples + otherwise, não ocorreu. Prefira **simples** quando o campo for reutilizado depois, ou normalize o valor num JavaScript antes da condição e use a saída dele.

---

## 8. Templates `{{{...}}}`

Qualquer campo texto de `configurations` aceita template. A substituição acontece antes da execução e aparece resolvida na rastreabilidade.

| Referência | Resultado [V] |
|---|---|
| `{{{webhook-sync-trigger.inBody}}}` | corpo recebido inteiro |
| `{{{webhook-sync-trigger.inBody.campo}}}` | campo |
| `{{{webhook-sync-trigger.inBody.lista.[0].nome}}}` | item de array (note o `.` antes de `[0]`) |
| `{{{webhook-sync-trigger.inHeader.<header>}}}` | header recebido (não houve header customizado no teste; veio vazio) |
| `{{{id1}}}` / `{{{id1.campo}}}` | saída de step REST |
| `{{{id-javascript1.output.campo}}}` | saída de JavaScript |
| `{{{splitter-start1.inBody.item}}}` ou `{{{splitter-start1.item}}}` | item do splitter (também `index`, `size`) |
| `{{{global-error-start.inBody.message}}}` | mensagem do erro (também `code`, `stackTrace`, `request.headers`, `request.body`, `response.headers`, `response.body`) |
| `{{{function.<idFn>.<saída>}}}` | resultado de função |
| `{{{var.tenant.<chave>}}}` / `{{{var.project.<chave>}}}` | variável (publicou com `var.tenant.tenantid`) |

Regras de renderização [V]:

- Em JSON (Resposta síncrona, `inBody`): objeto, array e número **sem aspas** (`"obj": {{{x.inBody}}}`); string **com aspas** (`"nome": "{{{x.nome}}}"`).
- Campo inexistente vira string vazia, sem erro. Se estiver sem aspas num JSON, o JSON quebra.
- Em JavaScript e condição avançada o valor entra como código-fonte (seções 6.2 e 7.4).

Variáveis: `GET /v2/variables?projectId={id}&page=1&pageSize=9999`. Tipos `TENANT` e `PROJECT`. Cadastre pela tela Ferramentas → Variáveis se faltar.

---

## 9. Funções

Funções não são caixas: ficam em `flow.functions` e são referenciadas nos templates. Parâmetros vão em **`params`**, não em `configurations`.

```json
"functions": {
  "id-function1": {
    "id": "id-function1", "type": "FUNCTION_UPPER_CASE", "name": "Upper case", "label": "Maiusculo",
    "componentId": "c1f2d51b-c71e-45d6-b9a5-3489836c8490",
    "originalComponentId": "c1f2d51b-c71e-45d6-b9a5-3489836c8490",
    "componentResourceId": "c9df28ce-7508-494e-9bd8-0d285b4296fd",
    "params": { "name": "Maiusculo", "string": "{{{webhook-sync-trigger.inBody.nome}}}" }
  }
}
```

Uso: `"{{{function.id-function1.string}}}"`.

Verificadas [V]: `FUNCTION_UPPER_CASE` (`fulano` → `FULANO`), `FUNCTION_SUM` (`1.25 + 2.5` → `"3.75"`, com `precision: 2`), `FUNCTION_DATE_TIME_GET` (`date`, `year`, ...).

| `type` | `componentResourceId` (última versão) | `params` | Saída |
|---|---|---|---|
| `FUNCTION_UPPER_CASE` | `c9df28ce-7508-494e-9bd8-0d285b4296fd` | `string`* | `string` |
| `FUNCTION_LOWER_CASE` | `dda0b869-b778-46ab-86e1-140c0deb82b9` | `string`* | `string` |
| `FUNCTION_SUM` | `68e244fd-78d6-41b0-9818-0ef9550bc6fd` | `sum.values`* (lista ≥2), `precision` | `sum` (string) |
| `FUNCTION_SUBTRACTION` | `da1dc93b-c6bc-4159-a976-36582a6be022` | `subtraction.values`*, `precision` | `subtraction` |
| `FUNCTION_MULTIPLICATION` | `dbf969ac-7597-41da-b154-3622e6eda1f1` | `multiplication.values`*, `precision` | `multiplication` |
| `FUNCTION_DIVISION` | `9ad4df56-cf4a-4705-b160-d06cac73a1f7` | `division.values`*, `precision` | `division` |
| `FUNCTION_DATE_TIME_GET` | `9803caf0-53ac-46cc-bd2f-4a0d59b155ec` | `format`* (ex. `yyyy-MM-dd`), `timezone` | `date`, `day`, `month`, `year`, ... |
| `FUNCTION_DATE_TIME_FORMAT` | `535e31f7-45e8-4f42-8839-7410e9074b84` | `date`*, `inputFormat`*, `outputFormat`* | idem |
| `FUNCTION_DATE_TIME_ADD` | `93c5066f-b701-4c91-9069-349b72fc7f72` | `date`*, `format`*, `unit`*, `amount`* | [S] |
| `FUNCTION_DATE_TIME_DIFF` | `7dec0548-7a8d-4193-b9c7-885e9ce1e50e` | `date1`*, `format1`*, `date2`*, `format2`* | [S] |
| `FUNCTION_DATE_TIME_IS_DATE_TIME` | `7bdd3fb0-b730-45cd-a3fb-4067ac197631` | `date`*, `format`* | [S] |
| `FUNCTION_LENGTH` | `7451cc34-a8e1-4b3a-b9f3-0125654c314f` | `text`* | [S] |
| `FUNCTION_SIZE` | `70903ebf-4e9f-4a65-afcb-0bd133ca9378` | `array`* | [S] |
| `FUNCTION_SUBSTRING` | `e8b41474-c11c-4e7a-84c6-43a5f7b34232` | `text`*, `beginIndex`*, `endIndex` | [S] |
| `FUNCTION_REPLACE` | `2549df63-ee77-403a-94a0-57c382f2e9f9` | `text`*, `oldChar`*, `newChar`* | [S] |
| `FUNCTION_BASE64_ENCODER` / `_DECODER` | `1a71f7ae-...` / `56ada54a-...` | `input`* | [S] |
| `FUNCTION_JOLT` | `cdf8e2f3-d1a7-4203-845c-dc8c28d711c5` | `input`, `spec`* | [S] |
| `FUNCTION_AGGREGATE` | `64cf1d2d-ce1b-48df-a4da-f53c466d2182` | `aggregate.inputs`* (≥2 objetos) | `output` |

A chave da saída é a do `outputSchema` do recurso (`GET /v3/utility-resources?utilityId=c1f2d51b-...`). `{{{function.<id>}}}` sem campo devolve o objeto `{ <saída>, params }`.

Função sem entrada válida (campo inexistente) retorna vazio/zero, sem erro [V].

---

## 10. Splitter (iteração) — só assíncrono [V]

O splitter guarda o subfluxo **dentro de `configurations.subFlow`**:

```json
"id-splitter1": {
  "id": "id-splitter1", "name": "Splitter", "type": "SPLIT", "label": "Itera itens",
  "hidden": false, "isDropped": true, "positions": { "top": "9000px", "left": "9280px" },
  "subFlowName": "Itera itens",
  "originalComponentId": "1b35a577-25ae-41e3-b6ba-d7530a066b93-splitter",
  "connections": { "next": [], "previous": ["webhook-hook-trigger"] },
  "configurations": {
    "name": "Itera itens",
    "path": "{{{webhook-hook-trigger.inBody.itens}}}",
    "subFlow": {
      "async": false, "start": "splitter-start1",
      "activities": {
        "splitter-start1": {
          "id": "splitter-start1", "type": "SPLIT_START", "label": "Splitter Start",
          "positions": { "top": "9077px", "left": "8983px" },
          "originalComponentId": "8f55959c-83ba-4fde-91d7-7ab6c3638822",
          "connections": { "next": ["id-javascript2"], "previous": [] }
        },
        "id-javascript2": { "...": "steps do subfluxo, com previous: ['splitter-start1']" }
      }
    }
  }
}
```

Comportamento [V]:

- Cada item gera uma **mensagem filha** (`sourceType: SPLITTED`, `originMessageId` = mensagem original). A original mostra `totalSplitMessage`.
- No subfluxo, `{{{splitter-start1.item}}}`, `.index` e `.size` (também com `.inBody.` no meio).
- **O fluxo principal termina no splitter.** Um step ligado depois do splitter no fluxo principal **não executou** (`finalComponent` = o splitter). Tudo que for por item vai **dentro** do subfluxo.
- Subfluxo aceita condições; splitter aninhado existe no front (`setSplitterSubFlow` é recursivo) [S].

---

## 11. Global error — só assíncrono [V]

Um por diagrama. Duas partes: a caixa `id-global-error` em `activities` (sem ligações) e o fluxo em `flow.globalErrorFlow`.

```json
"id-global-error": {
  "id": "id-global-error", "name": "Global error", "type": "GLOBAL_ERROR", "label": "Global error",
  "hidden": false, "isDropped": true, "positions": { "top": "9400px", "left": "9280px" },
  "configurations": {}, "originalComponentId": "98e39adf-35b6-49e6-8a3c-2de9cb370395-global-error",
  "connections": { "next": [], "previous": [] }
}
```

```json
"globalErrorFlow": {
  "start": "global-error-start",
  "activities": {
    "global-error-start": {
      "id": "global-error-start", "type": "GLOBAL_ERROR_START", "label": "Global Error Start",
      "positions": { "top": "9077px", "left": "8983px" },
      "originalComponentId": "f6e8b5a9-3960-437f-943d-6e32ae9195c9",
      "connections": { "next": ["id-javascript4"], "previous": [] }
    },
    "id-javascript4": { "...": "tratamento, com previous: ['global-error-start']" }
  }
}
```

Comportamento [V]:

- Dispara em **erro de execução** (ex.: exceção em JavaScript). **Não dispara** em Throw Exception.
- Os steps do tratamento aparecem na mesma mensagem, depois do step que falhou. A mensagem continua `ERROR`.
- Dados: `{{{global-error-start.inBody.message}}}` (ex.: `Error: boom proposital`), `.code`, `.stackTrace`, `.request.body` (payload original), `.request.headers`, `.response.*`.

---

## 12. Salvar, publicar, executar e rastrear

### 12.1 Salvar e publicar [V]

```
POST /v2/integrations/sketch/{integrationId}    # rascunho
POST /v2/integrations/publish/{integrationId}   # publica e ativa
```

Corpo: `{ "name", "description", "flow", "icons": [], "dynamicIcons": true }`.

- A rota é **v2**; em v3/v4 responde `No static resource`.
- `icons` (**array**) e `dynamicIcons` (**boolean**) são obrigatórios no publish; sem eles, `400` com corpo vazio. `dynamicIcons: []` dá `500 JSON parse error`.
- `name` é obrigatório (sem ele: `null value in column "name"`).
- Cada sketch/publish cria uma **revisão nova** com novo `diagramId`; o `integrationId` fica. Só uma revisão fica `PUBLISHED`, as anteriores viram `ARCHIVED`. Para editar, leia sempre a revisão atual:

```
GET /v3/integrations?id={integrationId}&lastVersion=true&fieldsReturn=id,diagramId,flow,name,status
GET /v3/integrations?id={integrationId}&allVersions=true      # histórico
GET /v3/integrations?diagramId={diagramId}                    # revisão específica
```

Ler sem `lastVersion=true` e republicar sobrescreve o diagrama com uma versão antiga.

O publish valida o flow no motor. Falha típica: `500 FLUIG_CONNECTOR_0011` com `FLUIG_CONNECTOR_ENGINE_0011` em `args`, **sem dizer qual step**. Diagnóstico: bissecção, publicando variantes com um componente por vez. Causas encontradas: componente não permitido para o gatilho; campos extras (`serviceId`/`applicationService` no Throw Exception).

O sketch **não** valida no motor: um flow inválido salva como rascunho sem erro.

### 12.2 Executar [V]

A chave do webhook: `GET /v3/keys?integrationId={id}` → `{ apiKey, sync, url }`.

| Gatilho | Chamada |
|---|---|
| Webhook síncrono | `POST https://api-ipaas.totvs.app/sync-hook/api/v1/integrations/{id}/api-key/{apiKey}` → `{ messageId, result, status }` |
| Webhook | `POST https://api-ipaas.totvs.app/ipaas/api/v1/integrations/{id}/api-key/{apiKey}` → `{ messageId, status }` (processa em segundo plano) |

`/execute` com Bearer respondeu 401; a forma com `api-key` no path é a que funciona. Os dois endpoints aceitam chamada sem autenticação além da apiKey: trate a apiKey como segredo.

**A chave não muda quando o gatilho muda.** Um diagrama criado síncrono e trocado para Webhook continuou com `sync: true`; chamar o `sync-hook` deixou as mensagens presas em `PROCESSING`. Chame a rota do **tipo atual** do gatilho.

### 12.3 Rastrear [V]

```
GET /v4/messages/{messageId}
GET /v3/steps/{integrationId}/{createdDate}/{messageId}      # createdDate da mensagem, URL-encoded
GET /v4/messages?page=1&pageSize=10&sourceTypes=SPLITTED&originMessageId={id}
    &initialDate={ISO +00:00}&finalDate={ISO +00:00}&status=DONE&status=ERROR&status=PROCESSING
```

Mensagem: `status` (`PROCESSING`, `DONE`, `ERROR`), `initialComponent`, `finalComponent` (rótulo do último step), `totalSplitMessage`, `errorStack`.

Cada step traz `componentId`, `status`, `inMessage`, `outMessage` e, nos nós de condição, **`condition: { expression, result }`** com a expressão já resolvida. É o melhor instrumento de depuração de desvios. O nó de condição aparece com `componentId` = id da Condição; o Otherwise aparece igual, mas sem `condition`.

Datas na listagem: use `+00:00` (formato do front). `sourceTypes` é obrigatório; valores aceitos vistos: `ORIGINAL`, `SPLITTED`.

Tela equivalente: `https://ipaas.totvs.app/message/{messageId}` (abas Geral e Rastreabilidade, com mensagens filhas).

---

## 13. Dados que não devem ser alterados

| Item | Por quê |
|---|---|
| `originalComponentId`, utilityIds, `componentResourceId` de funções (seções 6.1 e 9) | IDs globais da plataforma, iguais em todos os diagramas |
| IDs de auth model (seção 3.2) | Globais do tenant |
| Ids reservados de step: `webhook-sync-trigger`, `webhook-hook-trigger`, `global-error-start`, `splitter-start<n>`, `id-global-error` | O front e o motor reconhecem por esses nomes |
| `integrationId` de diagramas existentes | Estável; nunca recrie para "atualizar" |
| Diagramas `Valida *` do projeto `Validação apps` e diagramas de outros usuários | Evidência de validação dos apps; não reutilize como rascunho |
| Serviço `Api` do app nativo `API BRASIL` e apps com `isCustom: false` | Catálogo TOTVS, fora do nosso controle |
| Data Storage de outros diagramas (ex.: chaves de `Create book`) | Compartilhado no tenant |
| `apiKey` de webhook, tokens de conta | Segredos; não grave em arquivo |

Não fixe `diagramId` em nada: ele muda a cada save.

---

## 14. Receita para o agente

### 14.1 Antes de montar

1. Validar a sessão (seção 2) e confirmar o tenant com o usuário (produção).
2. Levantar por GET tudo que os steps precisam (seção 3.1): app, serviço, recurso e seus campos, ambiente, conta ativa. E as variáveis: `GET /v2/variables?projectId={id}&page=1&pageSize=9999`.
3. **Ambiente ou conta faltando: cadastre** (seções 3.3 e 3.4), pedindo a credencial ao usuário. Conta inativa: `PUT` com `active: true`. **App, serviço ou recurso faltando: pare** e avise o usuário que o aplicativo precisa ser cadastrado antes.
4. Escolher o gatilho pela seção 5; se precisar de Splitter, Global error ou Throw Exception, o gatilho é Webhook assíncrono.

### 14.2 Montar e validar

1. Pedir ao usuário para criar o diagrama em branco no projeto certo (ou criar pela UI) e obter o `integrationId` (seção 3.5).
2. Gerar o flow com ids da seção 4.2, `originalComponentId` da 6.1 e setas da 4.3.
3. `sketch` → `publish`. Se der `ENGINE_0011`, bissecção (12.1).
4. Executar com um payload para **cada ramo** (cada condição e o otherwise).
5. Ler os steps: conferir `condition.expression`/`result`, o `finalComponent` e o `result` da resposta.
6. Abrir o builder em `/builder/{diagramId atual}` e conferir visualmente caixas e setas.

### 14.3 Componente ainda não verificado

1. Arrastar o componente para um diagrama de rascunho pela UI e **Salvar rascunho**.
2. Ler o flow com `lastVersion=true` e copiar o formato exato (`type`, `originalComponentId`, campos).
3. Preencher `configurations` pelo schema (`/v3/utility-resources`), publicar e executar.
4. Registrar o resultado neste documento, trocando [S] por [V].

---

## 15. Erros conhecidos

| Sintoma | Causa | Ação |
|---|---|---|
| `403 Could not verify the provided CSRF token` | `sketch/project/{projectId}` fora do front | Criar o diagrama pela UI |
| `500 FLUIG_CONNECTOR_0011` / `ENGINE_0011` no publish | Componente não permitido para o gatilho ou campo inválido | Bissecção; ver seção 5 e 6.1. A versão anterior continua no ar |
| Ramo errado executa | `internalGroup: []`, `groupOperator` no lugar errado, condições não exclusivas | Ver 7.3; ler `condition.expression` no step |
| Condição booleana nunca casa | `== true` na avançada | `expected: "true"` na simples ou `== 'true'` |
| String com aspas simples (`"'A'"`) na saída | Condição avançada avaliada antes no fluxo | Usar condição simples ou normalizar em JavaScript |
| `200` com `error: "Unexpected character..."` | Resposta síncrona renderizou JSON inválido | Aspas em strings, sem aspas em objeto/número (seção 8) |
| Mensagem presa em `PROCESSING` com `finalComponent: 0-START` | Chamou `sync-hook` num diagrama com Webhook assíncrono | Usar a rota do tipo atual (12.2) |
| Step depois do Splitter não executa | O fluxo principal termina no splitter | Mover para dentro do subfluxo |
| Diagrama sem setas no builder | Falta `finalConnections` | Seção 4.3 |
| Tela de rastreabilidade em skeleton | Resposta síncrona sem `originalComponentId` | Seção 6.2 (Resposta síncrona); republicar e executar de novo |
| 401 nas chamadas da API | Token expirou (~48h) | Pedir novo login |
| Step REST com 401 do fornecedor | Conta desativada por `PUT` sem `active: true`, credencial trocada ou allowlist de IP no fornecedor | Conferir `active` na listagem de contas; pedir credencial nova |
| Ambiente sem autenticação depois de criado | Enviou `authModels` em vez de `authModelIds` | `PUT /v2/environments/{id}` com `authModelIds` |
| `500 Name is null` ao criar conta | `environments: [{id}]` em vez de `environmentId` | Seção 3.4 |

---

## 16. Estado deixado no tenant

| Item | Valor |
|---|---|
| Diagrama de teste | `ZZ Playbook - condicoes (teste)`, `integrationId` `a661937e-4697-4b90-ac95-5efb71e75c2a`, projeto `Validação apps` |
| Última versão publicada | Webhook síncrono → JavaScript → condição avançada / otherwise → 2 respostas |

Pode ser reutilizado para novos testes de componente (seção 14.3) ou excluído pela interface. A exclusão por API não foi testada.

Não verificado nesta rodada: Timer, E-mail, FTP, JDBC, Jolt, XSLT, Generator, Converter, Diagram Caller, Message Broker, SmartLink, Data Storage em execução, splitter aninhado e condição dentro de subfluxo.
