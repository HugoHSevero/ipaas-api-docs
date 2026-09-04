# Open-Meteo

APIs meteorológicas gratuitas e **sem autenticação** (`NO_AUTH`) para uso não comercial. Cobrem previsão do tempo, qualidade do ar, clima, ensemble, enchentes, histórico, meteorologia marinha, previsão sazonal e elevação.

- Site: https://open-meteo.com
- Código e spec oficial: https://github.com/open-meteo/open-meteo (pasta [`/openapi`](https://github.com/open-meteo/open-meteo/tree/main/openapi))
- Autenticação: nenhuma (`NO_AUTH`) para os endpoints públicos
- Licença de uso: CC BY 4.0, uso não comercial

## Por que vários ambientes

Cada domínio do Open-Meteo é servido por um **subdomínio diferente** (`api`, `air-quality-api`, `climate-api`, …). Como o `baseURL` fica no **ambiente** do iPaaS e o serviço se vincula a um ambiente, o app tem **um ambiente por subdomínio**. `Previsão do Tempo` e `Elevação` compartilham `api.open-meteo.com`, então dividem o mesmo ambiente.

Os subdomínios `customer-*` (planos pagos, exigem `apikey`) foram descartados das specs; ficam apenas as origens públicas.

## Cadastro no iPaaS

### 1. Aplicativo

| Campo | Valor |
|---|---|
| Nome | `Open-Meteo` |
| Descrição | APIs meteorológicas gratuitas: previsão, qualidade do ar, clima, ensemble, enchentes, histórico, marinha, sazonal e elevação |

### 2. Ambientes

Um ambiente por subdomínio, todos `REST` com autenticação `NO AUTH` e base path **sem barra no final** (os paths da spec já começam com `/v1/...`):

| Ambiente | Base path |
|---|---|
| `api.open-meteo.com` | `https://api.open-meteo.com` |
| `air-quality-api.open-meteo.com` | `https://air-quality-api.open-meteo.com` |
| `climate-api.open-meteo.com` | `https://climate-api.open-meteo.com` |
| `ensemble-api.open-meteo.com` | `https://ensemble-api.open-meteo.com` |
| `flood-api.open-meteo.com` | `https://flood-api.open-meteo.com` |
| `archive-api.open-meteo.com` | `https://archive-api.open-meteo.com` |
| `marine-api.open-meteo.com` | `https://marine-api.open-meteo.com` |
| `seasonal-api.open-meteo.com` | `https://seasonal-api.open-meteo.com` |

### 3. Conta

Não é necessária. Com `NO_AUTH` o ambiente funciona sem conta associada.

### 4. Serviços e importação

Cada serviço usa **Importar Swagger** apontando para a URL raw da spec dereferenciada correspondente. Importe sempre o `*.ipaas.json`, nunca o `openapi-*.json`.

| Serviço | Ambiente | Path | Spec (`openapi-*.ipaas.json`) |
|---|---|---|---|
| Previsão do Tempo | `api.open-meteo.com` | `/v1/forecast` | `openapi-forecast.ipaas.json` |
| Elevação | `api.open-meteo.com` | `/v1/elevation` | `openapi-elevation.ipaas.json` |
| Qualidade do Ar | `air-quality-api.open-meteo.com` | `/v1/air-quality` | `openapi-air-quality.ipaas.json` |
| Clima | `climate-api.open-meteo.com` | `/v1/climate` | `openapi-climate.ipaas.json` |
| Ensemble | `ensemble-api.open-meteo.com` | `/v1/ensemble` | `openapi-ensemble.ipaas.json` |
| Enchentes | `flood-api.open-meteo.com` | `/v1/flood` | `openapi-flood.ipaas.json` |
| Histórico Meteorológico | `archive-api.open-meteo.com` | `/v1/archive` | `openapi-historical.ipaas.json` |
| Meteorologia Marinha | `marine-api.open-meteo.com` | `/v1/marine` | `openapi-marine.ipaas.json` |
| Previsão Sazonal | `seasonal-api.open-meteo.com` | `/v1/seasonal` | `openapi-seasonal.ipaas.json` |

URL base de importação:

```
https://raw.githubusercontent.com/dugabriel/ipaas-api-docs/main/open-meteo/<spec>.ipaas.json
```

A importação aceita **URL**, não upload. O repositório precisa continuar público.

## Endpoints incluídos

9 operações, uma por serviço. Todas `GET` com parâmetros em query string (`latitude` e `longitude` são obrigatórios em quase todas):

| Serviço | Método | Path | Obrigatórios |
|---|---|---|---|
| Previsão do Tempo | GET | `/v1/forecast` | `latitude`, `longitude` |
| Elevação | GET | `/v1/elevation` | `latitude`, `longitude` |
| Qualidade do Ar | GET | `/v1/air-quality` | `latitude`, `longitude` |
| Clima | GET | `/v1/climate` | `latitude`, `longitude`, `start_date`, `end_date` |
| Ensemble | GET | `/v1/ensemble` | `latitude`, `longitude` |
| Enchentes | GET | `/v1/flood` | `latitude`, `longitude` |
| Histórico Meteorológico | GET | `/v1/archive` | `latitude`, `longitude`, `start_date`, `end_date` |
| Meteorologia Marinha | GET | `/v1/marine` | `latitude`, `longitude` |
| Previsão Sazonal | GET | `/v1/seasonal` | `latitude`, `longitude` |

## Como as specs foram geradas

As specs oficiais do Open-Meteo já vêm recortadas por domínio e em OpenAPI 3.1.0 (YAML), sem `$ref`. O processamento para este repositório:

1. Download de cada arquivo de `github.com/open-meteo/open-meteo/openapi`.
2. Conversão para OpenAPI **3.0.3 JSON** (o importador do iPaaS só foi validado com OpenAPI 3; os scripts do repositório leem JSON).
3. Os `servers` por-path viraram um `servers` na raiz, mantendo só a origem pública (sem `customer-*`).
4. `python3 tools/dereference.py open-meteo` gerou os `*.ipaas.json`. As specs já não tinham `$ref`, mas o passo padroniza a saída e valida `tags`/`summary`.

## Observações de uso

Respostas trazem `latitude`/`longitude` reais (grid mais próximo, podem diferir das coordenadas enviadas), `generationtime_ms`, `timezone` e blocos `hourly`/`daily`/`current` conforme os parâmetros pedidos. As séries (`hourly.time`, `hourly.temperature_2m`, …) vêm como **arrays paralelos**: o índice `i` de cada array corresponde ao mesmo instante em `time[i]`.

Erros retornam `{ "error": true, "reason": "..." }` com HTTP 400 — por exemplo, `latitude`/`longitude` ausentes ou intervalo de datas inválido.

`current`, `hourly` e `daily` aceitam listas de variáveis separadas por vírgula. Peça só as variáveis necessárias para reduzir o tamanho da resposta.

Uso não comercial e sem SLA. Trate indisponibilidade da origem como cenário esperado. Para uso comercial ou alto volume, o Open-Meteo oferece os subdomínios `customer-*` com `apikey` — não cobertos aqui.
