# Cloudinary

Plataforma de gestão de mídia: upload, armazenamento, transformação e entrega de imagens, vídeos e arquivos. Primeiro app do catálogo com autenticação `BASIC` — o quarto padrão viável do playbook (ao lado de `NO_AUTH`, `TOKEN` e `API_KEY`).

- Documentação: https://cloudinary.com/documentation
- Admin API: https://cloudinary.com/documentation/admin_api
- Upload API: https://cloudinary.com/documentation/image_upload_api_reference
- Autenticação: `BASIC` — `api_key` como usuário e `api_secret` como senha (HTTP Basic Auth)

| Ambiente | Base URL |
|---|---|
| Produção (US) | `https://api.cloudinary.com/v1_1` |
| Europa (EU) | `https://api-eu.cloudinary.com/v1_1` |
| Ásia-Pacífico (AP) | `https://api-ap.cloudinary.com/v1_1` |

O `cloud_name` **não** entra no base path do ambiente: ele é parâmetro de caminho em cada operação (`{cloud_name}`), preenchido via `configurations.inPath` no diagrama. Assim a mesma conta atende qualquer cloud name sem recriar ambiente — mesmo padrão usado no WhatsApp com `phone_number_id`.

## Não existe spec OpenAPI oficial

O Cloudinary **não publica** uma spec OpenAPI para download. A documentação é web + SDKs. As specs deste diretório foram montadas à mão a partir da referência oficial (Admin API e Upload API), cobrindo o núcleo de gestão de mídia. Isso difere do Asaas/Brevo (spec oficial) e se aproxima da BrasilAPI (endpoints derivados da documentação).

**Validado em execução.** App cadastrado no tenant `iPaaS Gateway` (produção), conta `BASIC` criada e diagrama `Valida Cloudinary` executado `DONE` (4,0s, `errorStack` nulo): ping, upload por URL, upload por base64 (Data URI) e detalhe do asset encadeando `{{{id3.public_id}}}`. As duas imagens foram criadas de verdade no cloud. Confirmado também que o iPaaS entrega o corpo do Upload API (form-encoded na origem) corretamente via `inBody` — ver IDs e detalhes abaixo.

## Obter as credenciais

1. Crie uma conta gratuita em https://cloudinary.com.
2. No Console, vá em **Settings → API Keys**.
3. Copie o **Cloud name**, a **API Key** e a **API Secret**.

A API Key e a API Secret são a credencial da conta `BASIC` no iPaaS. O Cloud name vai no `inPath` dos steps, não na conta.

Não versione a API Secret neste repositório. O `ipaas.json` descreve apenas o formato da autenticação.

## Cadastro no iPaaS

### 1. Aplicativo

| Campo | Valor |
|---|---|
| Nome | `Cloudinary` |
| Descrição | Plataforma de gestão de mídia: upload, armazenamento, transformação e entrega de imagens, vídeos e arquivos. |

### 2. Ambiente

| Campo | Valor |
|---|---|
| Nome | `Produção` |
| Tipo | `REST` |
| Base path | `https://api.cloudinary.com/v1_1` |
| Autenticação | `BASIC` |

### 3. Conta

A conta é obrigatória — sem ela as chamadas retornam 401.

| Campo | Valor |
|---|---|
| Nome | `Produção` |
| Tipo de autenticação | `BASIC` |
| Usuário (`username`) | sua API Key |
| Senha (`password`) | sua API Secret |

Valide a credencial chamando `GET /{cloud_name}/ping` (serviço `Metadados e Conta`) ou executando o diagrama — não pelo `testAccount` da interface, que não é confiável para esse fim (ver playbook, seção 2.3).

### 4. Serviços e importação

Quatro serviços, um por domínio:

| Serviço | Operações | Spec |
|---|---|---|
| `Upload` | 6 | `openapi-upload.ipaas.json` |
| `Recursos` | 7 | `openapi-recursos.ipaas.json` |
| `Pastas` | 5 | `openapi-pastas.ipaas.json` |
| `Metadados e Conta` | 10 | `openapi-metadados.ipaas.json` |

URLs de importação:

```
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/cloudinary/openapi-upload.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/cloudinary/openapi-recursos.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/cloudinary/openapi-pastas.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/cloudinary/openapi-metadados.ipaas.json
```

## Como as specs foram geradas

Escritas à mão a partir da referência oficial, recortadas por domínio e dereferenciadas:

```bash
py tools/dereference.py cloudinary
```

(No Windows o interpretador é `py`; em Linux/macOS use `python3`.) O script resolve os `$ref`, mescla `allOf` e valida os requisitos do importador do iPaaS. Rodou sem avisos: todas as operações têm `tags` e `summary`, e nenhum `array` sem `items` no `requestBody`.

## Domínios cobertos e de fora

O recorte atual cobre o núcleo de gestão de mídia (28 operações):

- **Upload** (Upload API): `upload`, `explicit`, `rename`, `destroy`, `tags`, `context`.
- **Recursos** (Admin API): listar por tipo, detalhar por public_id, listar por tag, buscar, atualizar, excluir em lote, restaurar.
- **Pastas** (Admin API): listar raiz, listar subpastas, criar, renomear/mover, excluir.
- **Metadados e Conta** (Admin API): `ping`, `usage`, `config`, listar tags, listar transformações, CRUD de `metadata_fields`.

Fora do recorte atual, da documentação oficial: `metadata_rules`, `people`, `resources_last_access_reports`, `streaming_profiles`, `triggers`, `upload_mappings`, `upload_presets`, `folder_operations` (roles/permissions), geração de assets do Upload API (`explode`, `generate_archive`, `multi`, `text`) e a Provisioning API (gestão de conta, credencial e base URL próprias). Para adicionar qualquer um, inclua as operações numa spec fonte e rode o `dereference.py`.

## Observações e armadilhas

- **O corpo das operações de escrita não é importado** (limitação do importador, playbook seção 4). Upload, explicit, rename, destroy, tags, context, update de recurso e criação de metadata field têm `requestBody` nas specs, mas o builder não traz os campos — monte o corpo em `configurations.inBody` no diagrama. Os schemas de corpo nas specs servem de referência dos campos esperados.

- **Upload API é form-encoded, não JSON.** A API real recebe `multipart/form-data` ou `x-www-form-urlencoded`. As specs declaram `application/json` por ser o que o builder entende; como o corpo é montado em `inBody` na execução, isso não afeta o resultado. **Não verificado** se o iPaaS envia o corpo como form-encoded para a Cloudinary — confirmar na primeira execução de um `POST /upload`.

- **`cloud_name` em todo path.** Toda operação tem `{cloud_name}` como primeiro segmento. Nos steps do diagrama, preencha `configurations.inPath.cloud_name` com o cloud name da conta.

- **Rate limit só na Admin API.** A Admin API é limitada (500 req/h no plano free, 2000+ nos pagos); a Upload API não tem limite de taxa. O serviço `Metadados e Conta` e parte do `Recursos` consomem a cota da Admin API.

- **Data centers EU/AP.** Contas premium podem usar `api-eu` ou `api-ap`. Se for o caso, troque o base path do ambiente — as specs são agnósticas quanto a isso.

- **Path param órfão zera a importação (armadilha nova).** A primeira versão do serviço `Recursos` tinha o `DELETE` no path `.../{type}/{public_id}` mas declarava só `public_ids` (query) nos parâmetros — o `{public_id}` do template ficou sem o parâmetro `in: path` correspondente. OpenAPI inválido, e o importador do iPaaS responde HTTP 200 e **zera as 7 operações do serviço em silêncio**, mesmo sintoma do `array` sem `items`. Custou uma bissecção inteira para isolar. Corrigido movendo o `DELETE` para `.../{resource_type}/{type}` (o endpoint real de delete em lote, que seleciona por query). O `tools/dereference.py` agora detecta path params não declarados.

## Estado no tenant (iPaaS Gateway, produção)

| Item | Id |
|---|---|
| App `Cloudinary` (`componentId`) | `3230d94e-64ce-45d2-85a0-2f937d0c045b` |
| Ambiente `Produção` (`https://api.cloudinary.com/v1_1`) | `bae51566-ae3f-4d77-9e70-71e1af049e67` |
| Conta `Produção` (`BASIC`) | `65090553-82ea-40d7-9be0-5cb92cc08c36` |
| Serviço `Upload` (6 recursos) | `cc428be6-51da-4252-8b02-0164d8a1e1e9` |
| Serviço `Recursos` (7 recursos) | `9b8ce73b-a9ec-4e5d-bc3b-8305265e1299` |
| Serviço `Pastas` (5 recursos) | `44a8162e-9219-422f-ab8f-6ff0f6a9e637` |
| Serviço `Metadados e Conta` (10 recursos) | `ed936eb3-ce24-4e9a-96f3-741ddb80cca6` |
| Diagrama `Valida Cloudinary` (`integrationId`) | `5dd03c5f-d6e9-4548-a4ff-5b94114707a6` |

Cloud name usado na validação: `z1hdjfbz` (vai no `configurations.inPath.cloud_name` dos steps, não na conta nem no ambiente). A credencial `BASIC` da conta (API Key `353984244296654` + API Secret) foi usada na validação e **deve ser rotacionada** — a API Key passou por chat.
