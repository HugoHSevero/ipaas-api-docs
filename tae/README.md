# TOTVS Assinatura Eletrônica - TAE

Plataforma de assinatura eletrônica da TOTVS (TOTVS Sign). O fluxo base é: login na API de identidade (gera token JWE) → upload do documento → criação da publicação → acompanhamento e download.

- Documentação: https://totvs-sign.readme.io/reference/introducao
- Jornadas (diagramas de integração): https://totvs-sign.readme.io/reference/jornadas
- Specs oficiais: Swashbuckle, uma por versão, baixa anônima, em `https://totvssign.staging.totvs.app/<api>/swagger/v<N>/swagger.json`. A lista de versões de cada API está em `configObject.urls` no `index.html` do Swagger UI.
- Autenticação: `Authorization: Bearer <token JWE>`, token obtido em `POST /identityintegration/v3/auth/login` com `userName` e `password`

| Ambiente | Base URL |
|---|---|
| Produção | `https://totvssign.totvs.app` |
| Homologação | `https://totvssign.staging.totvs.app` |

O cadastro no iPaaS usa **produção**. A homologação precisa ser provisionada por e-mail ao time do TAE (ver a página de introdução da documentação) e vale 60 dias. As bases de homologação e produção são separadas.

## Serviços

Seis serviços, um por API do TAE. Cada spec junta todas as versões publicadas da API, então rotas descontinuadas e suas substitutas aparecem lado a lado. O `summary` oficial avisa quando a rota será descontinuada.

| Serviço | API (prefixo do path) | Versões | Operações | Spec |
|---|---|---|---|---|
| `Identidade` | `/identityintegration` | v1, v2, v3 | 28 | `openapi-identidade.ipaas.json` |
| `Documentos` | `/documents` | v1 a v4 | 38 | `openapi-documentos.ipaas.json` |
| `Assinaturas` | `/signintegration` | v1, v2, v3 | 31 | `openapi-assinaturas.ipaas.json` |
| `Contatos` | `/contact` | v1, v2 | 23 | `openapi-contatos.ipaas.json` |
| `Webhooks` | `/webhooks` | v1 | 7 | `openapi-webhooks.ipaas.json` |
| `Dead Letter` | `/deadletter` | v1 | 4 | `openapi-deadletter.ipaas.json` |

### Por que os paths têm prefixo

No swagger oficial o `servers` é relativo (`/documents`) e os paths começam na versão (`/v1/publicacoes/...`). Com o ambiente em `https://totvssign.totvs.app`, o iPaaS montaria `https://totvssign.totvs.app/v1/publicacoes/...`, e o certo é `https://totvssign.totvs.app/documents/v1/publicacoes/...`. Sem ajuste, seriam necessários seis ambientes, um por API.

Por isso o `gerar.py` acrescenta o `servers` de cada API no começo de cada path (`/documents/v1/publicacoes/{idDocumento}/anexos`). Com isso, **um único ambiente** com base `https://totvssign.totvs.app` (sem barra no final) atende os seis serviços.

URLs de importação (para importar logo após um push, troque `main` pelo SHA do commit, ver seção 4 do playbook):

```
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-identidade.ipaas.json
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-documentos.ipaas.json
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-assinaturas.ipaas.json
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-contatos.ipaas.json
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-webhooks.ipaas.json
https://raw.githubusercontent.com/HugoHSevero/ipaas-api-docs/main/tae/openapi-deadletter.ipaas.json
```

## Como as specs foram geradas

```bash
python3 tae/gerar.py          # baixa os 14 swagger.json do staging e gera openapi-*.json
python3 tools/dereference.py tae
```

`gerar.py` faz só quatro ajustes:
- junta as versões de cada API;
- prefixa os paths com o `servers` da API;
- renomeia schemas homônimos com conteúdo diferente (não houve nenhum caso);
- preenche `summary` vazio com `operationId` ou `MÉTODO path`.

As specs oficiais já são OpenAPI 3.0.1, têm `tags` em todas as operações e declaram a segurança em header (`Bearer`, `apiKey`, `in: header`, nome `Authorization`). Nenhuma das armadilhas de HTTP 500 do importador se aplica, e o `dereference.py` não emitiu avisos.

Os swaggers foram baixados do **staging**, que é onde a documentação aponta. Não foi conferido se o swagger de produção é idêntico.

## Autenticação no iPaaS — não verificado

O token JWE vem de um login e **expira**. A validade não foi medida. Opções:

1. **Conta `API_KEY`** com `addTo: header`, chave `Authorization` e valor `Bearer <token>`. É o que o `ipaas.json` descreve. É simples, mas a conta precisa ser atualizada a cada expiração do token. O `PUT` exige `active: true` (seção 2.3 do playbook).
2. **Ambiente `NO_AUTH` e login dentro do diagrama:** primeiro um step `POST /identityintegration/v3/auth/login` e depois o token passado no header `Authorization` dos steps seguintes. O importador cria esse header em cada recurso a partir do `securityScheme`. Não depende de token fixo, mas a resposta do login não tem schema na spec (ver abaixo), então o mapeamento do token não foi testado.

## Limitações conhecidas da spec oficial

**130 das 131 operações não declaram schema de resposta.** Elas aparecem só como `"200": { "description": "OK" }`. A única com schema é `POST /signintegration/v1/assinaturas/digital/nuvem`. No iPaaS, os recursos importam sem campos de saída. Para mapear retornos (id do envelope no upload, id da publicação, token do login), os schemas precisam ser derivados de chamadas reais. Não foram inventados.

**Upload é `multipart/form-data`** (`POST /documents/v1/envelopes/upload`, campo `Envelope` com arquivos binários). O importador não traz o corpo de POST/PUT, e o envio de arquivo binário pelo iPaaS não foi testado.

## Cadastro

`cadastrar.js` faz app, ambiente, serviços e importação pela API, colado no console do DevTools numa aba logada do iPaaS. Primeiro rode com `CRIAR = false`, que só lê: sessão, tenant e o que já existe. Depois rode com `CRIAR = true` e o `SHA` do commit. O script reaproveita o que já existir com o mesmo nome e não cria a conta.

## Estado

| Etapa | Situação |
|---|---|
| Specs geradas (6 serviços, 131 operações) | feito |
| Commit/push | feito, `8711c47` no branch `add-tae` do fork `HugoHSevero` (URLs por SHA conferidas: HTTP 200 anônimo) |
| App, ambiente, serviços e importação no iPaaS | pendente |
| Conta | pendente |
| Execução de diagrama `DONE` | **não validado** |
