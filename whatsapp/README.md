# WhatsApp

WhatsApp Business Cloud API, hospedada pela Meta. Permite que a empresa fale com clientes no WhatsApp sem contratar um BSP (Business Solution Provider) e sem hospedar o cliente on-premises: as chamadas vão direto para a Graph API.

- Documentação: https://developers.facebook.com/documentation/business-messaging/whatsapp
- Spec oficial: https://github.com/facebook/openapi (`business-messaging-api_v23.0.yaml`)
- Autenticação: `TOKEN` (Bearer no header `Authorization`)
- Base URL: `https://graph.facebook.com/v23.0`

A Meta publica OpenAPI oficial em repositório próprio, o que coloca este app no caminho do recorte automatizado (como Asaas e Brevo) em vez de spec escrita à mão (como BrasilAPI). O link para o repositório está no fim da página de get-started e **não aparece no HTML servido por `curl`** — a página é renderizada por JavaScript, então é preciso abrir no navegador para achá-lo.

## Obter o token permanente

O token que o painel oferece no fluxo de introdução é **temporário** e não serve para cadastrar a conta no iPaaS. O permanente sai por outro caminho:

1. Crie o app em https://developers.facebook.com/apps com o caso de uso **Conectar-se com clientes pelo WhatsApp** e vincule um portfólio empresarial.
2. Em **Configuração da API**, conecte ou crie uma conta do WhatsApp Business (WABA) e guarde o **WABA ID** e o **ID do número de telefone de teste**.
3. Vá em **Configurações do negócio → Usuários do sistema** e crie um usuário do sistema.
4. Em **Atribuir ativos**, dê ao usuário **Controle total** sobre o app e sobre a conta do WhatsApp Business.
5. Clique em **Gerar token** e marque as permissões `whatsapp_business_messaging`, `whatsapp_business_management` e `business_management`.

O `phone_number_id` não é um dado de configuração do app: ele entra como **parâmetro de caminho** em cada operação (`POST /{Phone-Number-ID}/messages`). A mesma conta do iPaaS atende vários números.

## Como as specs foram geradas

```bash
curl -sL "https://raw.githubusercontent.com/facebook/openapi/main/business-messaging-api_v23.0.yaml" -o /tmp/meta.yaml
python3 tools/prepare_whatsapp.py /tmp/meta.yaml /tmp/whatsapp_fonte.json
python3 tools/slice_spec.py /tmp/whatsapp_fonte.json whatsapp \
    "mensagens=mensagens" "templates=templates" "numeros=numeros" \
    "contas=contas" "grupos=grupos"
python3 tools/dereference.py whatsapp
```

O `prepare_whatsapp.py` existe porque a spec da Meta precisa de quatro tratamentos antes do recorte. Todos estão documentados no cabeçalho do script; o resumo do **porquê** está abaixo.

## Decisões de modelagem

**`openapi: 3.1.0` foi baixado para `3.0.3`.** As cinco specs já validadas no iPaaS são 3.0.x e não há evidência de que o importador aceite 3.1 — o playbook não cobre o caso. O rebaixamento é quase gratuito porque a spec da Meta é 3.1 apenas no cabeçalho: zero `type` como lista, zero `$defs`, zero `webhooks`, e usa `nullable`, que é keyword de 3.0. A única marca real de 3.1 era um `const`, convertido para `enum` de um item.

**`/{Version}` saiu do path e foi para a URL do server.** Na spec original todos os 78 paths começam com `/{Version}/`, declarado como path parameter obrigatório. Mantido assim, cada operação importada pediria `Version` = `v23.0` como entrada em todo fluxo do iPaaS. Com a versão no server (`https://graph.facebook.com/v23.0`), o campo desaparece das 70 operações. O custo é que **trocar de versão da Graph API exige regerar as specs**, não reconfigurar o ambiente.

**`Authorization`, `User-Agent` e `Content-Type` foram removidos dos parâmetros.** A Meta os declara explicitamente em cada operação. No iPaaS quem injeta o Bearer é a conta cadastrada, então esses parâmetros apareceriam como campos manuais duplicando a credencial — e um `Authorization` preenchido à mão no fluxo sobrescreveria o da conta.

**Toda operação foi retagueada em um de cinco domínios.** A spec da Meta tem 56 tags, a maioria com uma ou duas operações, e 13 operações **sem tag nenhuma** (grupos e o receptor de webhook) — que fariam a importação falhar com HTTP 500 pela armadilha da seção 4 do playbook. O `tag_by_path.py` não serve aqui porque ele deriva a tag do primeiro segmento do path, que nessa spec é sempre `{Version}`. O mapa é por path e não por tag porque as tags originais se contradizem entre métodos do mesmo path: `GET /{WABA-ID}/message_templates` é `Templates`, mas `POST` no mesmo path é `Flows,Send Flow`.

## Recorte

| Serviço | Operações | Conteúdo |
|---|---|---|
| `mensagens` | 11 | envio de mensagens, mensagens criptografadas, marketing, mídia, histórico, chamadas |
| `templates` | 5 | templates de mensagem por WABA e por ID |
| `numeros` | 29 | registro, verificação, configurações, perfil comercial, QR codes, bloqueio de usuários, commerce, compliance |
| `contas` | 13 | WABA, usuários atribuídos, atividades, agendamentos, assinaturas de webhook |
| `grupos` | 12 | criação, participantes, link de convite, solicitações de entrada |
| `parceiros` | 30 | soluções multiparceiro, WABAs de clientes, números pré-verificados, portfólio empresarial, linha de crédito, intents de migração e OBO |

Total: **100 operações** das 113 da spec oficial.

O serviço `parceiros` ficou fora do recorte inicial, por ser superfície de revenda. Foi reincluído porque a **coexistência** — manter o número funcionando no app do WhatsApp Business e na Cloud API ao mesmo tempo — só é onboardada por Cadastro Incorporado, e isso exige ser Tech Provider ou Solution Partner da Meta. O fluxo de cadastro em si **não é REST**: é navegador, com SDK de Login do Facebook, seleção de portfólio e leitura de QR code pelo app. O que este serviço cataloga é a gestão em volta dele.

Todos os seis serviços usam o **mesmo ambiente e a mesma conta**: a base URL e o modelo de autenticação são idênticos, então não há motivo para ambiente separado.

## Domínios deixados de fora

**Flows** (13 operações: `Flows`, `Create Flow`, `Update Flow`, `Business Encryption`) — formulários interativos dentro da conversa. É um domínio grande e coerente, com ciclo de vida próprio (rascunho, publicação, depreciação) e criptografia de endpoint próprio. Cabe como um sétimo serviço quando houver caso de uso; para adicionar, inclua os paths de `{Flow-ID}` e `{WABA-ID}/flows` no `MAPA` do `prepare_whatsapp.py`.

**`POST /whatsapp/webhooks`** — não é endpoint chamável: é a documentação do **payload que a Meta envia** para o seu servidor. Importar viraria um recurso que o iPaaS tentaria chamar na Graph API. Para receber webhooks, o caminho é um receptor que responda ao handshake `GET` com `hub.challenge` — o webhook do iPaaS **não serve** para isso: ele só aceita `POST` e responde `403` no `GET`, verificado.

## Cadastro no iPaaS

Importado e **validado em diagrama** no tenant `iPaaS Gateway`. Os IDs estão na seção 10 do [playbook](../IPAAS-PLAYBOOK.md).

O diagrama `Valida WhatsApp` encadeia um recurso de cada um dos cinco serviços e executou `DONE` em 11,4s, com os cinco payloads reais na resposta síncrona. O primeiro step é `POST /messages`, que entregou uma mensagem de template de verdade no celular do destinatário.

A conta usa o token de **usuário do sistema** (`type: SYSTEM_USER`, `expires_at: 0`). Ao gerá-lo, se a Meta disser "Nenhuma permissão disponível — atribua uma função do app ao usuário do sistema", falta atribuir o **app** como ativo com `Gerenciar app`: o token é emitido para um app, e sem função nele não há permissão a oferecer. Se o app não aparecer na lista de ativos, ele não está no portfólio empresarial (Contas → Aplicativos → Adicionar um app).

O `phone_number_id` e o WABA ID entram nos steps via `configurations.inPath`, não na configuração do ambiente.

O importador exigiu duas descobertas que valem para qualquer app e estão na seção 4 do playbook:

**A importação é assíncrona.** `POST /import-swagger` responde HTTP 200 com corpo vazio e continua processando; listar os recursos na hora devolve zero e parece falha. O tempo medido até aparecerem foi de cerca de 1,9 segundo, igual para specs de 2 KB e de 340 KB. Faça polling.

**`type: array` sem `items` no `requestBody` zera a importação inteira, em silêncio.** HTTP 200, corpo vazio, nenhum recurso criado — nem os das outras operações. Na spec da Meta, `template.components[].parameters` vinha sem `items` e derrubava as 11 operações deste serviço de mensagens. O comportamento é assimétrico: em `responses` o mesmo defeito é tolerado (o Trello importa 45 operações tendo um). O `prepare_whatsapp.py` declara o schema correto em `ITEMS_FALTANDO` e o `dereference.py` passou a acusar o caso.

## Validação

Executado contra a API real em 2026-09-18, com o número de teste da Meta. Nenhum identificador real está neste repositório — ele é público.

**Diagrama `Valida WhatsApp`: execução `DONE` em 11,4s**, com os cinco serviços em cadeia e os payloads reais agregados na resposta síncrona. `errorStack` nulo e os 7 steps com status `DONE`. O step de envio recebeu `accepted` da Meta — mas **a mensagem não foi entregue no aparelho**, por restrição da conta de teste descrita abaixo. A execução valida o cadastro, o contrato e a autenticação; não valida a entrega.

**`POST /{Phone-Number-ID}/messages`** — HTTP 200 também em chamada direta. A resposta real confere **campo por campo** com o schema gerado, incluindo `messages[].message_status`:

```json
{ "messaging_product": "whatsapp",
  "contacts": [{ "input": "...", "wa_id": "..." }],
  "messages": [{ "id": "wamid...", "message_status": "accepted" }] }
```

Também em HTTP 200: `GET /{Phone-Number-ID}` (serviço `numeros`), `GET /{Phone-Number-ID}/settings`, `GET /{Phone-Number-ID}/whatsapp_business_profile`, `GET /{Phone-Number-ID}/message_qrdls`, `GET /{Phone-Number-ID}/block_users`, `GET /{Phone-Number-ID}/groups` (serviço `grupos`), `GET /{WABA-ID}` e `GET /{WABA-ID}/activities`, `/schedules`, `/subscribed_apps` (serviço `contas`), `GET /{WABA-ID}/message_templates` (serviço `templates`) e `GET /{WABA-ID}/phone_numbers`.

Os cinco serviços têm ao menos uma operação exercitada contra a API real.

`v23.0` e `v25.0` devolvem resposta idêntica no mesmo GET. A versão da URL foi mantida em `v23.0` por ser a que a spec oficial documenta — a Meta versiona o arquivo bem atrás da API disponível, e no momento só existe `business-messaging-api_v23.0.yaml` no repositório dela.

### O número de teste da Meta não entrega no Brasil

**Os envios são aceitos e nunca entregues.** A API responde `200` com `message_status: accepted`, o diagrama do iPaaS executa `DONE`, e a mensagem não chega ao aparelho. O motivo só aparece no webhook de status:

```json
"errors": [{ "code": 130497,
  "title": "Business account is restricted from messaging users in this country." }]
```

A causa é a restrição de mensagens **cross-country** da Meta: o número de teste é sempre americano (`+1 555-...`), o destinatário está no Brasil, e a Meta bloqueia esse tráfego para contas novas e sem verificação de negócio — a WABA de teste vem com `business_verification_status: not_verified`. O Brasil está entre os países com restrição adicional, junto com a Indonésia.

Nenhuma configuração do lado do iPaaS ou da spec contorna isso. Não é lista de permissão, não é template, e não é o nono dígito do número brasileiro — a Meta resolve `55DD9NNNNNNNN` para um `wa_id` de 12 dígitos, sem o 9 extra, mas isso é normalização normal e não impede a entrega. Para entregar de verdade a um destinatário brasileiro é preciso **registrar um número próprio na WABA e completar a verificação do negócio**.

Consequência para quem for validar um app de mensageria aqui: **`DONE` no diagrama não prova entrega.** O iPaaS considera sucesso o HTTP 200 e a Meta considera sucesso o `accepted`; nenhum dos dois vê o que acontece depois. Para saber, é obrigatório ler o evento `statuses` no webhook. A WABA de teste já vem inscrita no app **WA DevX Webhook Events**, visível no painel da Meta — foi ali que o `130497` apareceu.

### O que não foi validado

**`GET /{Phone-Number-ID}/call_permissions` e `POST /{Phone-Number-ID}/calls`** — HTTP 400 com `Calling API not enabled`. É gate de configuração do número, não ausência do endpoint, então foram mantidos na spec. Para habilitar: WhatsApp Manager, ou `POST /{Phone-Number-ID}/settings` com configuração de `calling`.

**Todas as operações de escrita, exceto o envio de mensagem.** Criar template, criar QR code, bloquear usuário, criar grupo, registrar número e assinar webhook não foram exercitados. Só `POST /{Phone-Number-ID}/messages` foi.

**`GET /me/businesses` depende do escopo `business_management`.** Com o token temporário do painel, que não o tem, responde `(#100) Missing Permission`; com o de usuário do sistema responde 200 — no caso desta conta, com `data` vazio, então o WABA ID continuou vindo do painel.

### A spec oficial documenta menos do que a API devolve

Comparando campo por campo as respostas reais com os schemas, a spec da Meta está incompleta em três dos quatro endpoints conferidos:

| Serviço | Campos que a API devolve e a spec não declara |
|---|---|
| `templates` | `parameter_format`, `disable_ios_autofill`, `is_primary_device_delivery_only`, `components[].buttons[].url` e todo o `components[].cards[]` (templates de carrossel) |
| `numeros` | `platform_type`, `throughput.level` em `/{WABA-ID}/phone_numbers` |
| `contas` | `message_template_namespace` em `/{WABA-ID}` |

Os campos ausentes foram acrescentados via `COMPLEMENTOS_*` no `prepare_whatsapp.py`, que só adiciona e nunca sobrescreve o que a Meta declara. Ter spec oficial **não** dispensa conferir contra resposta real: é o schema importado que os fluxos de integração conseguem mapear, e um campo ausente aqui é um campo inalcançável no iPaaS.

Ao acrescentar campo em spec com `$ref`, aplique o complemento **no destino** do `$ref`, nunca ao lado dele. Um `properties` irmão de um `$ref` (ou de um `allOf`) não se soma ao schema referenciado: o `dereference.py` resolve com `{**resolvido, **irmãos}`, e os irmãos vencem. Na primeira tentativa isso apagou os cinco campos de `WhatsAppBusinessAccountPhoneNumber` e deixou só os dois que eu havia adicionado — o diff contra a resposta real foi o que pegou. Para nó com `allOf`, entre como um membro novo da lista.

## Atenção ao token

O token oferecido no painel em **Configuração da API** é temporário: o `debug_token` mostra `type: USER` com `expires_at` no mesmo dia. Não serve para a conta do iPaaS, que pararia de funcionar em horas. Use o de usuário do sistema, descrito acima.

Para conferir qualquer token antes de cadastrar:

```bash
curl -s "https://graph.facebook.com/v23.0/debug_token?input_token=$T&access_token=$T"
```

O certo tem `type: SYSTEM_USER` e `expires_at: 0` (nunca expira). O errado tem `type: USER` e uma data próxima. Confira também `scopes`: o do painel vem sem `business_management`.

### "Nenhuma permissão disponível" ao gerar o token

Mensagem completa: *"Atribua uma função do app ao usuário do sistema ou selecione outro app para continuar."* A causa é a ordem do fluxo — o token é emitido **para um app**, e o usuário do sistema precisa ter função nesse app **antes** de gerar.

Em Configurações do negócio → Usuários do sistema → selecione o usuário → **Adicionar ativos** (não "Gerar token") → aba **Aplicativos** → marque o app → ative **Gerenciar app**. Repita em **Contas do WhatsApp** para a WABA, com **Gerenciar contas do WhatsApp Business**. Só então "Gerar token" oferece as permissões.

Se o app não aparecer na lista de ativos, ele não está no portfólio empresarial: Contas → Aplicativos → Adicionar → Adicionar um app. Apps criados pela conta de desenvolvedor pessoal não entram no portfólio automaticamente. O app e a WABA precisam estar no **mesmo** portfólio.

## Observações

O número de teste gratuito da Meta só envia para até **5 destinatários pré-verificados**, e a janela de atendimento de 24 horas precisa estar aberta (o destinatário respondeu) para mensagens fora de template. Para enviar a qualquer número é necessário verificação do negócio e um número próprio registrado.
