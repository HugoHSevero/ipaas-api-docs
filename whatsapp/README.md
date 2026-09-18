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

Total: **70 operações** das 113 da spec oficial.

## Domínios deixados de fora

**Flows** (21 operações: `Flows`, `Create Flow`, `Update Flow`, `Business Encryption`) — formulários interativos dentro da conversa. É um domínio grande e coerente, com ciclo de vida próprio (rascunho, publicação, depreciação) e criptografia de endpoint próprio. Cabe como um sexto serviço quando houver caso de uso; para adicionar, inclua os paths de `{Flow-ID}` e `{WABA-ID}/flows` no `MAPA` do `prepare_whatsapp.py`.

**Tudo de BSP/parceiro** (22 operações) — `Multi-Partner Solutions`, `OBO Mobility Intent`, `Pre-Verified Phone Numbers`, `MM Lite Onboarding`, `Solution Migration`, `Migration Intent`, `Application Business Connections`, `Client WhatsApp Business Accounts`, `Business Portfolio`, `Billing`. Só faz sentido para quem revende a plataforma para outras empresas, o oposto do caso de uso deste cadastro.

**`POST /whatsapp/webhooks`** — não é endpoint chamável: é a documentação do **payload que a Meta envia** para o seu servidor. Importar viraria um recurso que o iPaaS tentaria chamar na Graph API. Para receber webhooks no iPaaS, o caminho é um gatilho de webhook no diagrama, não um recurso REST.

## Cadastro no iPaaS

Importado no tenant `iPaaS Gateway`, com os 70 recursos conferidos. Os IDs estão na seção 10 do [playbook](../IPAAS-PLAYBOOK.md). **Falta a conta**, que exige o token permanente — e portanto falta a validação em diagrama.

O importador exigiu duas descobertas que valem para qualquer app e estão na seção 4 do playbook:

**A importação é assíncrona.** `POST /import-swagger` responde HTTP 200 com corpo vazio e continua processando; listar os recursos na hora devolve zero e parece falha. O tempo medido até aparecerem foi de cerca de 1,9 segundo, igual para specs de 2 KB e de 340 KB. Faça polling.

**`type: array` sem `items` no `requestBody` zera a importação inteira, em silêncio.** HTTP 200, corpo vazio, nenhum recurso criado — nem os das outras operações. Na spec da Meta, `template.components[].parameters` vinha sem `items` e derrubava as 11 operações deste serviço de mensagens. O comportamento é assimétrico: em `responses` o mesmo defeito é tolerado (o Trello importa 45 operações tendo um). O `prepare_whatsapp.py` declara o schema correto em `ITEMS_FALTANDO` e o `dereference.py` passou a acusar o caso.

## Validação

Executado contra a API real em 2026-09-18, com token temporário do painel e o número de teste da Meta. Nenhum identificador real está neste repositório — ele é público.

**`POST /{Phone-Number-ID}/messages`** — HTTP 200, mensagem de template entregue. A resposta real confere **campo por campo** com o schema gerado, incluindo `messages[].message_status`:

```json
{ "messaging_product": "whatsapp",
  "contacts": [{ "input": "...", "wa_id": "..." }],
  "messages": [{ "id": "wamid...", "message_status": "accepted" }] }
```

Também em HTTP 200: `GET /{Phone-Number-ID}` (serviço `numeros`), `GET /{Phone-Number-ID}/settings`, `GET /{Phone-Number-ID}/whatsapp_business_profile`, `GET /{Phone-Number-ID}/message_qrdls`, `GET /{Phone-Number-ID}/block_users`, `GET /{Phone-Number-ID}/groups` (serviço `grupos`), `GET /{WABA-ID}` e `GET /{WABA-ID}/activities`, `/schedules`, `/subscribed_apps` (serviço `contas`), `GET /{WABA-ID}/message_templates` (serviço `templates`) e `GET /{WABA-ID}/phone_numbers`.

Os cinco serviços têm ao menos uma operação exercitada contra a API real.

`v23.0` e `v25.0` devolvem resposta idêntica no mesmo GET. A versão da URL foi mantida em `v23.0` por ser a que a spec oficial documenta — a Meta versiona o arquivo bem atrás da API disponível, e no momento só existe `business-messaging-api_v23.0.yaml` no repositório dela.

### O que não foi validado

**`GET /{Phone-Number-ID}/call_permissions` e `POST /{Phone-Number-ID}/calls`** — HTTP 400 com `Calling API not enabled`. É gate de configuração do número, não ausência do endpoint, então foram mantidos na spec. Para habilitar: WhatsApp Manager, ou `POST /{Phone-Number-ID}/settings` com configuração de `calling`.

**Todas as operações de escrita, exceto o envio de mensagem.** Criar template, criar QR code, bloquear usuário, criar grupo, registrar número e assinar webhook não foram exercitados. Só `POST /{Phone-Number-ID}/messages` foi.

**`GET /me/businesses`** responde `(#100) Missing Permission` com token que não tem `business_management`. Sem ele não é possível descobrir a WABA a partir do token — o ID tem que vir do painel.

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

O token oferecido no painel em **Configuração da API** é temporário: o `debug_token` mostra `type: USER` com `expires_at` no mesmo dia. Não serve para a conta do iPaaS, que pararia de funcionar em horas. Use o permanente de usuário do sistema, descrito acima.

Para conferir qualquer token antes de cadastrar:

```bash
curl -s "https://graph.facebook.com/v23.0/debug_token?input_token=$T&access_token=$T"
```

Interessa `type`, `expires_at` e `scopes`. Um token de usuário do sistema não traz `expires_at` com data próxima.

## Observações

O número de teste gratuito da Meta só envia para até **5 destinatários pré-verificados**, e a janela de atendimento de 24 horas precisa estar aberta (o destinatário respondeu) para mensagens fora de template. Para enviar a qualquer número é necessário verificação do negócio e um número próprio registrado.
