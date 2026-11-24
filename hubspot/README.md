# HubSpot

Plataforma HubSpot na API **2026-09** (versionamento por data). Um app só no iPaaS, com **105 serviços e 1.187 operações**, organizados por domínio no nome do serviço (`CRM - Contatos`, `CMS - Posts do blog`...).

**Status: cadastrado e validado.** 105 serviços e 1.187 recursos importados no tenant `iPaaS Gateway`; diagrama `Valida HubSpot` executado `DONE` em 8,2s (listar proprietários → criar contato → ler o contato criado). IDs na seção 10 do [playbook](../IPAAS-PLAYBOOK.md).

- Documentação: https://developers.hubspot.com/docs/api-reference/latest/overview
- Fonte das specs: repositório oficial `HubSpot/HubSpot-public-api-spec-collection`, fixado no commit `44cabcc2fb54c96dbfc28103c85946542b984400` (`servicos.json`, campo `shaFonte`)
- Base URL: `https://api.hubapi.com` (as versões ficam no path, ex.: `/crm/objects/2026-09/contacts`)
- Autenticação: `TOKEN` (Bearer) com uma **service key** da HubSpot (*Configurações → Integrações → Service Keys*)

## Por que 2026-09

A HubSpot passou a versionar por data em março de 2026. Os endpoints `v1`–`v4` ficam sem suporte depois de setembro de 2027, e a documentação manda usar a versão por data mais recente em integrações novas.

## Arquivos

| Arquivo | O que é |
|---|---|
| `servicos.json` | A lista aprovada: cada serviço, seu domínio, a spec oficial de origem e as operações (`MÉTODO path`) que ele recebe. Fonte de verdade do recorte. |
| `gerar.py` | Baixa as specs oficiais pelo SHA, recorta por serviço, ajusta para o importador e grava os `.ipaas.json`. |
| `openapi-<serviço>.ipaas.json` | As 105 specs prontas para o `import-swagger`. |
| `ipaas.json` | App, ambiente, conta e serviços, no padrão das outras pastas. |

As specs oficiais **não** são versionadas (cada uma tem ~220 KB e há 104 delas). O `gerar.py` as baixa para `_fontes/`, que está no `.gitignore`:

```bash
py hubspot/gerar.py                      # os 105 serviços
py hubspot/gerar.py crm-contatos         # só alguns, pelo slug
```

## Como o recorte foi feito

- Para APIs publicadas em mais de um "rollout", ficou a variante com paths por objeto (`/crm/objects/2026-09/contacts`) e, nas outras, a de mais operações.
- **Cada operação pertence a um serviço só.** Várias specs repetem as mesmas operações genéricas (`/{objectType}/...`) e de associação; elas ficaram em `CRM - Objetos (genérico)` e `CRM - Associações`. Com isso seis specs viraram redundantes e não geram serviço: Agendamentos, Esquema de associações, Forecasts, Objetos personalizados e as duas de price books em leitura.
- `Webhooks` trazia embutidas as operações do Journal: virou `Assinaturas de webhooks` (9) e `Webhooks Journal` (26).
- `CMS/Pages` (66 operações) foi dividida em `Páginas de destino` (39) e `Páginas do site` (27), pelo path.

## Ajustes para o importador

- **Segurança:** as specs declaram `developer_hapikey` (query), `oauth2` e `private_apps` (header). Tudo foi trocado por um único `http bearer` em cada operação, como na spec do WhatsApp, que importou. **Não verificado** no HubSpot até o primeiro import.
- **Grupos circulares de schemas** explodem a dereferência (profundidade estoura ou o arquivo passa de dezenas de MB). Grupos com mais de 3 schemas que se referenciam em círculo viram objeto genérico em todos os pontos de uso:
  - Media Bridge: 86 schemas de uma linguagem de expressões (sem o corte, 29,7 MB num serviço só; com o corte, 1 MB).
  - Pipeline Governance e mais duas specs: 7 schemas de filtros (`PublicAndFilterBranch`...); sem o corte, a geração passava de 5 minutos sem terminar.
- **Ciclos simples** (um schema que contém a si mesmo: `ArrayFieldSchema`, `LayoutSection`, `PublicListFolder`, `ComboEventRuleBranch`) são truncados pelo `tools/dereference.py`, que antes abortava com `RecursionError`.
- **`$ref` sem destino na spec oficial:** o HubDB referencia `HubDbTableRowV3Wrapper`, que não existe na fonte. O ponto virou objeto genérico; não se inventou o schema.
- **`summary` ausente:** `POST /crm/objects/2026-09/{objectType}/search` vem sem `summary`; recebeu o `operationId`.

Conferido nos 105 arquivos: 1.187 operações batendo com `servicos.json`, 0 `$ref` restante, todas com `tags`, `summary` e `security` bearer. Total de ~37 MB; os maiores são as páginas e posts do CMS (~3,4 MB cada).

## Cadastro e validação

1. **Teste com um serviço pequeno.** `CRM - Proprietários` (2 operações) importou com os campos de resposta expandidos e um header `Authorization` em cada recurso, vindo do `http bearer`. Isso confirmou a troca de segurança antes do lote.
2. **Lote.** Os outros 104 serviços importaram completos em 6,6 minutos, incluindo as specs de ~3,5 MB do CMS.
3. **Conferência.** Os 1.187 recursos foram lidos um a um: nenhum com a resposta como `response` string. 265 sem campos de resposta, que batem com a spec: DELETE (108) e PUT (14) exatamente, GET (4 na spec, downloads e exports que não devolvem JSON). Sobram **6** (3 POST, 3 GET) em que a spec tem schema e o iPaaS não mostrou campos; suspeita de resposta que não é objeto (lista de textos, mapa livre), **não identificados**.
4. **Conta.** `TOKEN` com service key de uma conta HubSpot gratuita, escopos `crm.objects.owners.read`, `crm.objects.contacts.read` e `crm.objects.contacts.write`.
5. **Diagrama.** `Valida HubSpot`, 3 steps, `DONE` em 8,2s, `errorStack` nulo. O contato `265234707503` foi criado de verdade; cada execução cria outro.

### Credencial: service key

A HubSpot recomenda service keys para integrações de sistema a sistema numa única conta (beta público desde fevereiro de 2026). Fontes de terceiros dizem que a criação de **private apps legados** foi desligada em 28/09/2026 (contas novas) e 26/10/2026 (contas antigas); não confirmei na documentação oficial. A service key vai como Bearer, igual ao token de private app, e encaixa no modelo `TOKEN`.

A service key **só serve para chamadas REST**. Não funciona para webhooks, extensões de interface e o resto da plataforma de desenvolvedor. Na prática, os serviços com `{appId}` no path (Media Bridge, configurações de eventos de marketing, webhooks, extensões de CRM, gestão de apps) dependem de um app de desenvolvedor.

Os escopos dependem do que cada integração usa. As specs oficiais citam cerca de 77 escopos nas 1.187 operações, mas listam vários por operação sem deixar claro se são todos obrigatórios ou alternativos; por isso não há aqui uma tabela de escopos por serviço. 136 operações não declaram escopo (as com `{appId}`). Muitos escopos são de produtos pagos (CMS, e-mail de marketing, sequências, comércio) e podem não aparecer numa conta gratuita.

## O que não foi verificado

- Os outros 104 serviços não foram executados; só Proprietários e Contatos.
- Os 6 recursos com schema de resposta na spec e sem campos no iPaaS (ver acima).
- Em `CRM - Negócios` o path oficial usa o id do tipo (`/crm/objects/2026-09/0-3`) e não `/deals`. Não verificado se a API aceita os dois.
- Se o iPaaS tem limite de serviços por app.
- Os campos onde a estrutura foi cortada (grupos circulares) aparecem como objeto genérico no builder; o corpo real pode ser montado em `configurations.inBody`.
- Quatro grupos da documentação não têm spec `2026-09` no repositório oficial: `account/brands`, `account/ip-ranges`, `conversations/chat-configuration` e `marketing/forms`.
- Quais serviços funcionam numa conta gratuita: depende dos escopos que o plano oferece.

A service key usada na validação foi criada para este teste e **deve ser rotacionada**. Para trocar: `PUT /ipaas/api/v3/accounts/{id}` com o corpo completo e `active: true` explícito (playbook, seção 2.3).
