# Playbook — Cadastrar um número novo do WhatsApp e usá-lo no iPaaS

Guia operacional para quem **já tem o app WhatsApp cadastrado no iPaaS** (ambiente, conta e serviços importados) e quer **colocar um número próprio para enviar mensagens**. Cobre o que precisa ser feito no painel da Meta, o que precisa existir no iPaaS, e como validar o envio ponta a ponta.

Se o objetivo é montar o conector do zero (importar a spec, criar serviços), esse é outro trabalho — está no [README](./README.md) e no [playbook geral](../IPAAS-PLAYBOOK.md). Aqui o conector já existe; falta o número.

Tudo marcado como **verificado** foi executado com sucesso nesta conta. Nenhum identificador real (número, WABA ID, phone_number_id, token) está neste arquivo — o repositório é público.

---

## 0. O modelo mental, antes de tudo

A confusão mais cara é achar que cada número exige um cadastro novo no iPaaS. **Não exige.** No iPaaS, o app WhatsApp tem **um ambiente** e **uma conta**, e os dois são **compartilhados por todos os números**:

| Camada | Onde vive | Muda por número? |
|---|---|---|
| Base URL (`https://graph.facebook.com/v23.0`) | Ambiente do iPaaS | **Não** |
| Modelo de auth (`TOKEN`, Bearer) | Ambiente do iPaaS | **Não** |
| Token de acesso | Conta do iPaaS | **Não** (o token de usuário do sistema atende vários números) |
| `phone_number_id` | Parâmetro `inPath` de cada step do diagrama | **Sim** |
| `WABA-ID` | Parâmetro `inPath` de cada step do diagrama | **Sim** |

Ou seja: **cadastrar um número novo é trabalho quase todo no lado da Meta.** No iPaaS você só passa a usar o novo `phone_number_id`/`WABA-ID` como valor de parâmetro nos fluxos. Nada de novo ambiente, nova conta ou nova importação.

O que separa "aceito" de "entregue" também mora na Meta, não no iPaaS — ver seção 4.

---

## 1. O que você precisa ter na Meta

Um número entrega mensagem de verdade quando **três** condições são satisfeitas na Meta. Todas verificadas nesta sessão como necessárias:

1. **Número registrado e verificado** na WABA — `code_verification_status: VERIFIED`, `account_mode: LIVE`.
2. **Negócio (portfólio empresarial) verificado / WABA aprovada** — `account_review_status: APPROVED` na WABA.
3. **Token de usuário do sistema** com acesso ao app e à WABA — `type: SYSTEM_USER`, `expires_at: 0`.

Faltando a 1 ou a 2, a API **aceita** a mensagem (`HTTP 200`) e ela **não chega** — foi exatamente o caso do número de teste americano, que batia no erro `130497` ("Business account is restricted from messaging users in this country"), visível só no webhook de status. Com número brasileiro próprio verificado e WABA `APPROVED`, a entrega passou a funcionar (verificado nesta sessão, template e texto livre).

---

## 2. Passo a passo no painel da Meta

### 2.1 Adicionar o número à WABA

1. **WhatsApp Manager** (`business.facebook.com/wa/manage`) ou a **Configuração da API** do app em `developers.facebook.com/apps`.
2. Adicione o número de telefone à conta do WhatsApp Business (WABA).
3. Faça a **verificação por SMS ou ligação**: a Meta envia um código, você o informa, e o número passa a `code_verification_status: VERIFIED`.
4. O número precisa **não estar ativo em outro app do WhatsApp** (ou usar coexistência — fora do escopo deste guia; ver a seção "Coexistência" no [README](./README.md)).

Ao final, confirme pela API que está `VERIFIED` e `LIVE` (seção 3.2).

### 2.2 Verificar o negócio

Se a WABA vier com `account_review_status` diferente de `APPROVED`, a entrega para certos países (Brasil incluído) fica bloqueada. A verificação do negócio (Business Verification) é feita em **Configurações do negócio → Central de Segurança**, e é o passo que destrava o `130497`. Nesta conta a WABA está `APPROVED` e a entrega funciona.

### 2.3 Coletar os dois IDs do número

Na tela de **Configuração da API** aparecem lado a lado, e é comum confundir:

```
ID do número de telefone (phone_number_id):        <ID-A>   ← vai no inPath dos steps de número/envio
Identificação da conta do WhatsApp Business (WABA): <ID-B>   ← vai no inPath dos steps de WABA
```

**São números diferentes.** O `phone_number_id` identifica o número; o WABA ID identifica a conta que o contém. Enviar mensagem usa o `phone_number_id`; listar templates ou dados da conta usa o WABA ID.

> Se você tiver só o `phone_number_id`, dá para descobrir o WABA ID por API partindo do WABA e listando os números até achar o seu (seção 3.3). O caminho inverso (número → WABA) **não** é exposto por este token: `GET /{phone_number_id}?fields=whatsapp_business_account` responde `#100`.

### 2.4 Garantir o token de usuário do sistema

O token que o painel oferece em **Configuração da API** é temporário (`type: USER`, expira no mesmo dia) e **não serve**. O correto:

1. **Configurações do negócio → Usuários do sistema** → selecione (ou crie) o usuário do sistema.
2. **Adicionar ativos** → aba **Aplicativos** → marque o app → ative **Gerenciar app**.
3. **Adicionar ativos** → aba **Contas do WhatsApp** → marque a WABA → ative **Gerenciar contas do WhatsApp Business**.
4. **Gerar token** → marque `whatsapp_business_messaging`, `whatsapp_business_management` e `business_management`.

Se "Gerar token" disser *"Nenhuma permissão disponível — atribua uma função do app ao usuário do sistema"*, é porque faltou o passo 2 (o app precisa estar atribuído **antes** de gerar). Se o app não aparece na lista de ativos, ele não está no portfólio: **Contas → Aplicativos → Adicionar um app**. App e WABA precisam estar no **mesmo** portfólio.

Confira o token antes de usar:

```bash
curl -s "https://graph.facebook.com/v23.0/debug_token?input_token=$T&access_token=$T"
```

O certo tem `type: SYSTEM_USER`, `expires_at: 0` e, em `scopes`, os três acima. O errado tem `type: USER` e uma data de expiração próxima.

---

## 3. Descobrir e conferir os IDs por API

Todas as chamadas saem de dentro da página autenticada do iPaaS, reusando o token que já está na conta — ou você pode usar o token de sistema direto. Substitua `$T` pelo token.

### 3.1 Pegar o token que já está gravado na conta do iPaaS

```js
// rode no console da página https://ipaas.totvs.app já logada
const jwt = document.cookie.match(/(?:^|;\s*)jwt\.token=([^;]+)/)[1];
const appId = '<componentId do app WhatsApp>';           // ver seção 10 do playbook geral
const r = await fetch(`https://api-ipaas.totvs.app/ipaas/api/v3/accounts?componentId=${appId}&page=1&pageSize=100`,
  { headers: { authorization: 'Bearer ' + jwt, accept: 'application/json' } });
const acc = (await r.json()).items[0];
const T = acc.config.outputSchema.token;                 // token de sistema do WhatsApp
```

### 3.2 Conferir a saúde do número

```
GET https://graph.facebook.com/v23.0/{phone_number_id}?fields=id,display_phone_number,verified_name,code_verification_status,quality_rating,account_mode,messaging_limit_tier,status&access_token=$T
```

O que você quer ver: `code_verification_status: VERIFIED`, `account_mode: LIVE`, `status: CONNECTED`. `quality_rating` fica `UNKNOWN` até haver tráfego e depois vira `GREEN`/`YELLOW`/`RED`. `messaging_limit_tier` (ex.: `TIER_250`) é quantos números novos você pode iniciar conversa por dia.

### 3.3 Descobrir o WABA ID (se só tiver o phone_number_id)

Com o WABA ID em mãos, confirme que ele contém o seu número:

```
GET https://graph.facebook.com/v23.0/{WABA-ID}?access_token=$T
GET https://graph.facebook.com/v23.0/{WABA-ID}/phone_numbers?fields=id,display_phone_number,code_verification_status,account_mode&access_token=$T
```

O primeiro traz `name`, `account_review_status` (quer `APPROVED`) e `message_template_namespace`. O segundo lista os números da WABA — o seu `phone_number_id` deve aparecer ali com o `display_phone_number` certo.

### 3.4 Ver os templates aprovados

Texto livre só entrega na janela de 24h (seção 4). Para primeiro contato você precisa de um template aprovado:

```
GET https://graph.facebook.com/v23.0/{WABA-ID}/message_templates?fields=name,status,language,category&access_token=$T
```

Use um com `status: APPROVED`. `hello_world` costuma vir pré-aprovado.

---

## 4. Template vs. texto livre — a regra das 24h

O tipo de mensagem que entrega depende da **janela de atendimento**:

| Situação | O que entrega |
|---|---|
| Primeiro contato / destinatário não respondeu nas últimas 24h | **Só template aprovado** (`type: template`) |
| Destinatário te respondeu nas últimas 24h (janela aberta) | **Texto livre** (`type: text`) e qualquer tipo |

Verificado nesta sessão: o template entregou em primeiro contato; depois, com a janela aberta, o texto livre entregou. Um detalhe útil de diagnóstico — na resposta da API, o envio de texto na janela aberta volta **só com o `wamid`**, enquanto o de primeiro contato costuma vir com `message_status: accepted`.

**`HTTP 200` / `accepted` não prova entrega.** O iPaaS considera sucesso o 2xx da Meta e a Meta considera sucesso o `accepted`; nenhum dos dois enxerga o que acontece na entrega. A confirmação real está no **webhook de status** (evento `statuses`) ou no aparelho. Foi lá que o `130497` apareceu quando o número era o de teste.

---

## 5. Enviar direto pela Graph API (teste rápido, sem iPaaS)

Bom para isolar problemas de credencial/número antes de envolver o diagrama.

Template (funciona sem janela aberta):

```bash
curl -sX POST "https://graph.facebook.com/v23.0/{phone_number_id}/messages" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{ "messaging_product":"whatsapp", "to":"55DDDNNNNNNNN",
        "type":"template",
        "template":{ "name":"<template_aprovado>", "language":{ "code":"en_US" } } }'
```

Texto livre (só na janela de 24h aberta):

```bash
curl -sX POST "https://graph.facebook.com/v23.0/{phone_number_id}/messages" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{ "messaging_product":"whatsapp", "to":"55DDDNNNNNNNN",
        "type":"text", "text":{ "body":"sua mensagem" } }'
```

A Meta normaliza o número brasileiro: `55DD9NNNNNNNN` resolve para um `wa_id` de 12 dígitos (sem o 9 extra). Isso é normal e não impede a entrega.

---

## 6. Usar o número em um diagrama do iPaaS

Como ambiente e conta já existem, usar um número novo é só **preencher o `inPath` dos steps** com o `phone_number_id` (e o `WABA-ID` nos steps de conta/templates). Nenhum recadastro.

Num step REST do WhatsApp, os campos que importam:

```json
"configurations": {
  "accountId": "<id da conta Produção do iPaaS>",
  "environmentId": "<id do ambiente Produção do iPaaS>",
  "applicationService": "<id do serviço, ex. Mensagens>",
  "inPath": { "Phone-Number-ID": "<phone_number_id do número novo>" },
  "inBody": {
    "messaging_product": "whatsapp",
    "to": "55DDDNNNNNNNN",
    "type": "template",
    "template": { "name": "<template_aprovado>", "language": { "code": "en_US" } }
  }
}
```

Para trocar de número, muda-se **só** o valor de `Phone-Number-ID` (e `WABA-ID` onde houver). Para texto livre, troque o `inBody` por `{ "type":"text", "text": { "body":"..." } }`.

> **Lembrete do corpo:** o importador de swagger **não traz o corpo de POST**, então o `inBody` é montado à mão no step — como no exemplo acima. Isso é esperado (seção 4 do playbook geral).

### Fluxo de publicação e execução (reaproveitando o diagrama de validação)

O diagrama de validação já existe (ver seção 10 do playbook geral). Para exercitar um número novo nele:

1. `GET .../v3/integrations?id={integrationId}&lastVersion=true&fieldsReturn=id,flow,name,description,icons,dynamicIcons` — leia a revisão atual. **Sempre `lastVersion=true`**, senão você republica uma revisão velha.
2. No `flow`, troque `Phone-Number-ID`/`WABA-ID` nos `configurations.inPath` de cada step e ajuste o `inBody` do envio.
3. `POST .../v2/integrations/sketch/{integrationId}` com `{ name, description, flow, icons, dynamicIcons, descriptionEdit }`. **Mande `flow` como objeto, não string** — string dá `500 JSON parse error`. A rota é **v2**.
4. `POST .../v2/integrations/publish/{integrationId}` com o mesmo corpo. **`icons` (array) e `dynamicIcons` (boolean) são obrigatórios no publish** — sem eles, `400` sem corpo.
5. `GET .../v3/keys?integrationId={integrationId}` — pegue a `apiKey` do webhook síncrono.
6. `POST https://api-ipaas.totvs.app/sync-hook/api/v1/integrations/{integrationId}/api-key/{apiKey}` — executa.
7. `GET .../v4/messages/{messageId}` — confira `status: DONE`, `errorStack: null` e `finalComponent` igual ao último nó.

Verificado nesta sessão: com o número novo, a execução síncrona retornou `DONE`, o template e o texto livre foram enviados pela plataforma, e ambos chegaram no aparelho.

---

## 7. Checklist rápido para um número novo

- [ ] Número adicionado à WABA e **verificado** (`code_verification_status: VERIFIED`, `account_mode: LIVE`)
- [ ] WABA com `account_review_status: APPROVED` (negócio verificado) — senão, não entrega
- [ ] Token de sistema com acesso ao app e à WABA (`type: SYSTEM_USER`, `expires_at: 0`, escopos certos)
- [ ] `phone_number_id` e `WABA-ID` do número anotados (são IDs diferentes)
- [ ] Teste direto na Graph API: template entregou (primeiro contato) ou texto livre (janela aberta)
- [ ] No iPaaS, `inPath` dos steps atualizado com os IDs novos — **sem** criar ambiente/conta/importação
- [ ] Diagrama publicado e executado: `DONE`, e mensagem confirmada **no aparelho** (não só `accepted`)

---

## 8. Erros comuns e o que significam

| Sintoma | Causa provável |
|---|---|
| `200`/`accepted` mas não chega | Número/negócio não verificado (`130497`, no webhook de status), ou texto livre fora da janela de 24h |
| `#100 Tried accessing nonexisting field` ao ler a WABA | WABA ID errado, ou o token não tem acesso a essa WABA |
| Texto livre não entrega, template entrega | Janela de 24h fechada — use template ou peça o destinatário responder |
| "Nenhuma permissão disponível" ao gerar token | App não atribuído ao usuário do sistema antes de gerar (seção 2.4) |
| Token para de funcionar em horas | É o token temporário `type: USER` do painel; use o de usuário do sistema |
| `500 JSON parse error` ao salvar diagrama | `flow` enviado como string; mande objeto |
| `400` sem corpo no publish | Faltou `icons` (array) e/ou `dynamicIcons` (boolean) |
