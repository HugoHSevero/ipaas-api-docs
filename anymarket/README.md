# Anymarket

Hub brasileiro de integração com marketplaces (grupo olist): centraliza catálogo, estoque, preço, anúncios e pedidos de vários marketplaces em uma única API. Boa candidata para o catálogo: autenticação simples (API key em header), **especificação oficial publicada** e ambiente de sandbox.

- Documentação: https://developers.anymarket.com.br
- Índice de specs oficiais (machine-readable): https://developers.anymarket.com.br/specs/index.json
- Spec usada: **V2 API (backoffice)**, OpenAPI 3.0.0, `https://developers.anymarket.com.br/specs/backoffice.pt-BR.json`
- Autenticação: `API_KEY` no header `gumgaToken` (**não** usa `Authorization: Bearer`)

| Ambiente | Base URL |
|---|---|
| Sandbox | `https://sandbox-api.anymarket.com.br/v2` |
| Produção | `https://api.anymarket.com.br/v2` |

Os paths da spec são relativos (`/products`, `/orders`, `/stocks`), então o `/v2` fica no base path do ambiente.

## Por que a V2 e não a V3

O Anymarket publica três APIs relevantes no índice de specs:

| Spec | Operações | Autenticação | Observação |
|---|---|---|---|
| **backoffice (V2)** | 153 | `gumgaToken` no header | **usada aqui** — mapeia limpo para `API_KEY` do iPaaS |
| backoffice-v3 (V3) | 154 | OAuth2 client credentials (`POST /oauth2/token`) | mesmos endpoints; auth mais trabalhosa |
| marketplace | 23 | — | para quem implementa um marketplace |
| remote | 21 | — | API que o **marketplace** implementa (server aponta para o parceiro); fora de escopo |

A V2 e a V3 expõem os mesmos endpoints; a única diferença é a autenticação. Como o iPaaS tem um auth model `API_KEY` de header que encaixa direto no `gumgaToken`, a V2 é o caminho mais barato. A V3 (OAuth2) fica como evolução possível.

## Obter o token (gumgaToken)

O token é o identificador do lojista, gerado no painel do Anymarket. No sandbox, use o token da conta de sandbox. O mesmo valor vai no header `gumgaToken` de toda requisição:

```
gumgaToken: <seu_token>
```

Não versione o token neste repositório. O `ipaas.json` descreve apenas o formato da autenticação.

## Serviços (recorte por domínio)

As 153 operações da V2 foram recortadas em 5 serviços coerentes, agrupando as 32 tags da spec por domínio de negócio:

| Serviço | Operações | Tags agrupadas | Spec |
|---|---|---|---|
| `Catálogo` | 50 | Produto, SKU, Imagem, Marcas, Categorias, Grupo de característica, Tipos de variação, Valores de variação | `openapi-catalogo.ipaas.json` |
| `Anúncios e Transmissões` | 28 | SKU Marketplace, Transmissão, Template, Feed transmissão, Feed preço de transmissão | `openapi-anuncios-transmissoes.ipaas.json` |
| `Pedidos` | 32 | Pedido, Devolução, Perguntas, Mensageria, Feed pedido, Fulfillment, Documentos Fiscais, Emissão de Etiquetas, Cotar Frete | `openapi-pedidos.ipaas.json` |
| `Estoque e Preço` | 22 | Estoque, Local de Estoque, Feed reserva, Preço, Promoção, Campanhas | `openapi-estoque-preco.ipaas.json` |
| `Administração` | 21 | Usuários, Perfis de Acesso, Callback, Monitoramento de Erro | `openapi-administracao.ipaas.json` |

URLs de importação:

```
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/anymarket/openapi-catalogo.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/anymarket/openapi-anuncios-transmissoes.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/anymarket/openapi-pedidos.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/anymarket/openapi-estoque-preco.ipaas.json
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/anymarket/openapi-administracao.ipaas.json
```

## Cadastro no iPaaS

### 1. Aplicativo

| Campo | Valor |
|---|---|
| Nome | `Anymarket` |
| Descrição | Hub de integração com marketplaces (olist): catálogo de produtos e SKUs, anúncios e transmissões, pedidos, estoque, preço e administração. |

### 2. Ambiente

| Campo | Valor |
|---|---|
| Nome | `Sandbox` |
| Tipo | `REST` |
| Base path | `https://sandbox-api.anymarket.com.br/v2` |
| Autenticação | `API KEY` |

Há também um ambiente de `Produção` (`https://api.anymarket.com.br/v2`). Como os dois só diferem no subdomínio, um **ambiente custom** com placeholder e filhos (padrão do Asaas, seção 2.2 do playbook) evita duplicar os serviços — mas isso ainda **não foi montado** aqui.

### 3. Conta

Obrigatória — sem ela as chamadas retornam 401.

| Campo | Valor |
|---|---|
| Nome | `Sandbox` |
| Tipo de autenticação | `API KEY` |
| Adicionar em | `Header` |
| Chave | `gumgaToken` |
| Valor | seu token de sandbox |

### 4. Serviços e importação

Cinco serviços, um por domínio (ver tabela acima). Cada serviço importa a URL raw do `.ipaas.json` correspondente.

## Como as specs foram geradas

A spec oficial V2 já é OpenAPI 3.0.0, já traz `tags` em português e `summary` em toda operação, então **não precisa de conversão nem de injeção de tags**. O fluxo foi:

```bash
# 1. baixar a spec oficial V2 (aberta, sem auth)
curl -sL "https://developers.anymarket.com.br/specs/backoffice.pt-BR.json" -o /tmp/anymarket_v2.json

# 2. recortar por domínio (agrupando várias tags por serviço) e dereferenciar
python3 tools/dereference.py anymarket
```

O recorte por domínio agrupa **várias tags em um mesmo serviço**, o que o `tools/slice_spec.py` (uma tag por arquivo) não faz sozinho. Os cinco `openapi-*.json` fonte deste diretório já são o resultado desse agrupamento — bastando rodar o `dereference.py` para regenerar os `.ipaas.json`. Os grupos estão na tabela de serviços acima.

Dois ajustes foram necessários e viraram melhorias do repositório:

**Esquema de segurança órfão removido.** A spec V2 declara dois `securitySchemes`: `gumgaToken` (o real, header) e `authorization` (bearer, estilo V3, que vazou para a V2 e **não é referenciado por nenhuma operação**). Mantê-lo faria cada recurso importado ganhar um campo `authorization` inútil (playbook, seção 4). Foi removido dos recortes; só `gumgaToken` permanece.

**Schemas recursivos truncados.** A V2 tem dois schemas que referenciam a si mesmos: `CategoryChildren` (categoria com categorias filhas) e `PromotionRuleChildreenSubConditionResource` (regra de preço com subcondições aninhadas). O `tools/dereference.py` original abortava com `RecursionError` ao encontrar um `$ref` circular. Foi ajustado para, ao detectar o ciclo, emitir um **objeto genérico terminal** no ponto da recursão (`{"type": "object", "description": "Referência recursiva a … (truncada)"}`) em vez de crashar. Isso preserva os campos não recursivos e faz a árvore terminar; o console passa a listar os ciclos truncados. Correção geral, aproveita qualquer app com schema recursivo.

Resultado: 153 operações, 0 `$ref` restante, todas com `tags` e `summary`, apenas `gumgaToken` em `securitySchemes`.

## Validação

**Ainda não validado em diagrama.** O cadastro no iPaaS (app, ambiente, conta, serviços, importação) e a execução `DONE` em diagrama dependem de uma sessão autenticada e de um token de sandbox — pendentes. Enquanto não houver execução `DONE`, o app **não está validado**.

Pontos de atenção para a validação, herdados do playbook:

- O importador do iPaaS **não traz o corpo de POST/PUT**. Para exercitar escrita (criar produto, marca, etc.), o corpo vai em `configurations.inBody` no diagrama.
- Comece por GETs simples de sandbox (`GET /brands`, `GET /categories`, `GET /products`) antes de encadear escrita.
- Endpoints com parâmetro de path precisam de valor de teste em `configurations.inPath`.

## Observações

Os schemas vêm da **spec oficial do fornecedor** (V2, pt-BR). Nenhum retorno foi ainda confirmado contra respostas reais da API — fazer isso na etapa de validação.

Os campos `children` de categoria e de subcondição de promoção aparecem como objeto genérico nos recursos importados, por serem recursivos na origem (ver acima). A estrutura completa está na spec fonte.
