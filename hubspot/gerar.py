#!/usr/bin/env python3
"""Gera as specs do HubSpot para importação no TOTVS iPaaS.

A fonte é o repositório oficial de specs da HubSpot, fixado por commit em
`servicos.json` (`shaFonte`). Cada serviço do iPaaS é uma lista de operações
(`METODO path`) de uma das specs oficiais; `servicos.json` garante que nenhuma
operação aparece em dois serviços.

Para cada serviço o script:
  1. baixa a spec oficial (cache em `_fontes/`, fora do Git);
  2. mantém só as operações do serviço;
  3. troca os `securitySchemes` por um único `http bearer` (o app usa o modelo
     `TOKEN` do iPaaS; `oauth2` e `apiKey` em query não são aceitos/testados);
  4. chama `tools/dereference.py` (resolve `$ref`, `allOf`, `discriminator`);
  5. confere o resultado e grava `openapi-<slug>.ipaas.json` nesta pasta.

Uso:
    py hubspot/gerar.py                       # todos os serviços
    py hubspot/gerar.py crm-proprietarios     # só alguns (slugs)
"""

import copy
import json
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.setrecursionlimit(20000)  # Tarjan recursivo sobre grafos de centenas de schemas
sys.path.insert(0, str(AQUI.parent / "tools"))
import dereference  # noqa: E402

CACHE = AQUI / "_fontes"
BUILD = AQUI / "_build"
METODOS = ("get", "post", "put", "patch", "delete")
BASE_FONTE = "https://raw.githubusercontent.com/{repo}/{sha}/PublicApiSpecs/{rel}"
ESQUEMA = {
    "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "description": "Token de acesso de private app da HubSpot (modelo TOKEN do iPaaS).",
    }
}


def baixar(rel, repo, sha):
    """Baixa a spec oficial para o cache, se ainda não estiver lá."""
    destino = CACHE / rel.replace("/", "__")
    if destino.exists() and destino.stat().st_size:
        return destino
    url = BASE_FONTE.format(
        repo=repo, sha=sha, rel="/".join(urllib.parse.quote(p) for p in rel.split("/"))
    )
    with urllib.request.urlopen(url, timeout=120) as r:
        corpo = r.read()
    CACHE.mkdir(exist_ok=True)
    destino.write_bytes(corpo)
    return destino


def _existe(raiz, ref):
    """True se o $ref local aponta para algo que existe no documento."""
    if not ref.startswith("#/"):
        return False
    no = raiz
    for parte in ref[2:].split("/"):
        parte = parte.replace("~1", "/").replace("~0", "~")
        if not isinstance(no, dict) or parte not in no:
            return False
        no = no[parte]
    return True


def sanear_refs(no, raiz, quebrados):
    """Troca `$ref` sem destino por um objeto genérico.

    A spec oficial do HubDB referencia `HubDbTableRowV3Wrapper`, que não existe
    em `components.schemas` (defeito da fonte). O `dereference.py` aborta com
    KeyError nesse caso. Não se inventa o schema: o ponto vira um objeto genérico
    e o caso é listado no log, para constar no README.
    """
    if isinstance(no, dict):
        ref = no.get("$ref")
        if isinstance(ref, str) and not _existe(raiz, ref):
            quebrados.add(ref)
            return {
                "type": "object",
                "description": f"Referência a {ref.split('/')[-1]} que não existe na spec "
                               "oficial da HubSpot; estrutura desconhecida.",
            }
        return {k: sanear_refs(v, raiz, quebrados) for k, v in no.items()}
    if isinstance(no, list):
        return [sanear_refs(i, raiz, quebrados) for i in no]
    return no


PREFIXO = "#/components/schemas/"
# Grupos circulares maiores que isso são cortados. A expansão cresce de forma
# combinatória com o tamanho do grupo: 7 filtros de pipeline que se referenciam
# (Pipeline Governance) já passavam de 5 minutos sem terminar.
LIMITE_GRUPO = 3


def grupos_circulares(schemas):
    """Componentes fortemente conexos (Tarjan) do grafo de referências entre schemas."""
    grafo = {}
    for nome, corpo in schemas.items():
        alvos = set()
        pilha = [corpo]
        while pilha:
            n = pilha.pop()
            if isinstance(n, dict):
                ref = n.get("$ref")
                if isinstance(ref, str) and ref.startswith(PREFIXO) and ref[len(PREFIXO):] in schemas:
                    alvos.add(ref[len(PREFIXO):])
                pilha.extend(n.values())
            elif isinstance(n, list):
                pilha.extend(n)
        grafo[nome] = alvos

    indice, baixo, pilha, na_pilha, grupos = {}, {}, [], set(), []
    contador = [0]

    def visitar(v):
        indice[v] = baixo[v] = contador[0]
        contador[0] += 1
        pilha.append(v)
        na_pilha.add(v)
        for w in grafo[v]:
            if w not in indice:
                visitar(w)
                baixo[v] = min(baixo[v], baixo[w])
            elif w in na_pilha:
                baixo[v] = min(baixo[v], indice[w])
        if baixo[v] == indice[v]:
            grupo = []
            while True:
                w = pilha.pop()
                na_pilha.remove(w)
                grupo.append(w)
                if w == v:
                    break
            grupos.append(grupo)

    for v in grafo:
        if v not in indice:
            visitar(v)
    return grupos


def _cortar(no, membros):
    if isinstance(no, dict):
        ref = no.get("$ref")
        if isinstance(ref, str) and ref.startswith(PREFIXO) and ref[len(PREFIXO):] in membros:
            return {
                "type": "object",
                "description": "Estrutura recursiva da spec oficial da HubSpot (truncada); "
                               "ver a spec fonte.",
            }
        return {k: _cortar(v, membros) for k, v in no.items()}
    if isinstance(no, list):
        return [_cortar(i, membros) for i in no]
    return no


def cortar_grupos_grandes(spec, cortes):
    """Corta as referências internas de grupos circulares grandes.

    A spec da Media Bridge tem 86 schemas que se referenciam em círculo (uma
    linguagem de expressões em que toda função aceita qualquer outra). A
    dereferência expande cada caminho possível por esse grupo: a profundidade
    estoura e, mesmo cortando só as referências internas, o arquivo passa de
    29 MB, porque cada ponto de uso expande os 86 membros. Por isso qualquer
    referência a um membro do grupo vira um objeto genérico.
    """
    schemas = (spec.get("components") or {}).get("schemas") or {}
    membros = set()
    for grupo in grupos_circulares(schemas):
        if len(grupo) > LIMITE_GRUPO:
            membros |= set(grupo)
            cortes.append((len(grupo), sorted(grupo)[:4]))
    if not membros:
        return spec
    # toda referência a um membro, de dentro ou de fora do grupo, vira objeto genérico
    return _cortar(spec, membros)


def preparar(spec, quebrados, cortes):
    """Saneia a spec oficial uma vez por fonte, antes de fatiar por serviço."""
    spec = sanear_refs(spec, spec, quebrados)
    return cortar_grupos_grandes(spec, cortes)


def fatiar(spec, servico):
    """Devolve uma cópia da spec só com as operações do serviço."""
    quer = set(servico["operacoes"])
    novo = copy.deepcopy(spec)
    achadas = set()
    paths = {}
    for caminho, item in novo.get("paths", {}).items():
        mantido = {}
        for chave, valor in item.items():
            if chave in METODOS:
                id_op = f"{chave.upper()} {caminho}"
                if id_op in quer:
                    mantido[chave] = valor
                    achadas.add(id_op)
            else:
                mantido[chave] = valor  # `parameters` do path item etc.
        if any(m in mantido for m in METODOS):
            paths[caminho] = mantido
    faltam = quer - achadas
    if faltam:
        raise SystemExit(f"{servico['slug']}: operações que não existem na fonte: {sorted(faltam)[:3]}")
    novo["paths"] = paths

    # segurança: um único esquema bearer, aplicado a cada operação
    novo.setdefault("components", {})["securitySchemes"] = copy.deepcopy(ESQUEMA)
    novo.pop("security", None)
    for caminho, item in paths.items():
        for m in METODOS:
            if m in item:
                item[m]["security"] = [{"bearerAuth": []}]
                # o nome do recurso no iPaaS vem do summary; a spec oficial deixa
                # alguns em branco (ex.: busca genérica de objetos)
                if not item[m].get("summary"):
                    item[m]["summary"] = item[m].get("operationId") or f"{m.upper()} {caminho}"

    # cabeçalho enxuto e tags só das operações presentes
    usadas = []
    for item in paths.values():
        for m in METODOS:
            for t in (item.get(m) or {}).get("tags", []):
                if t not in usadas:
                    usadas.append(t)
    novo["info"] = {"title": f"HubSpot - {servico['servico']}", "version": "2026-09"}
    novo["servers"] = [{"url": "https://api.hubapi.com"}]
    novo["tags"] = [{"name": t} for t in usadas]
    return novo


def conferir(plano, servico):
    """Checagens que o dereference.py não faz."""
    problemas = []
    ops = [
        (m, c)
        for c, item in plano.get("paths", {}).items()
        for m in METODOS
        if m in item
    ]
    if len(ops) != len(servico["operacoes"]):
        problemas.append(f"{len(ops)} operações no arquivo, {len(servico['operacoes'])} esperadas")
    for caminho, item in plano.get("paths", {}).items():
        declarados = {p.get("name") for p in item.get("parameters", []) if p.get("in") == "path"}
        for m in METODOS:
            op = item.get(m)
            if not op:
                continue
            alvo = f"{m.upper()} {caminho}"
            decl = declarados | {p.get("name") for p in op.get("parameters", []) if p.get("in") == "path"}
            for nome in [s.split("}")[0] for s in caminho.split("{")[1:]]:
                if nome not in decl:
                    problemas.append(f"{alvo}: path param '{nome}' não declarado (o import zera a spec)")
            rb = op.get("requestBody")
            if rb is not None and not (rb.get("content") or {}):
                problemas.append(f"{alvo}: requestBody com content vazio (o import zera a spec)")
    return problemas


def main():
    escolhidos = set(sys.argv[1:])
    cfg = json.loads((AQUI / "servicos.json").read_text(encoding="utf-8"))
    servicos = cfg["servicos"]
    if escolhidos:
        desconhecidos = escolhidos - {s["slug"] for s in servicos}
        if desconhecidos:
            print(f"slugs desconhecidos: {sorted(desconhecidos)}")
            return 1
        servicos = [s for s in servicos if s["slug"] in escolhidos]

    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir()
    fontes = {}
    quebrados = set()
    cortes = []
    for s in servicos:
        if s["fonte"] not in fontes:
            caminho = baixar(s["fonte"], cfg["repositorioFonte"], cfg["shaFonte"])
            bruto = json.loads(caminho.read_text(encoding="utf-8"))
            fontes[s["fonte"]] = preparar(bruto, quebrados, cortes)
        spec = fatiar(fontes[s["fonte"]], s)
        (BUILD / f"openapi-{s['slug']}.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"HubSpot {cfg['versaoApi']} @ {cfg['shaFonte'][:10]}: {len(servicos)} serviço(s)")
    ok = dereference.processar(BUILD)

    total, problemas_total = 0, []
    for s in servicos:
        arq = BUILD / f"openapi-{s['slug']}.ipaas.json"
        plano = json.loads(arq.read_text(encoding="utf-8"))
        problemas = conferir(plano, s)
        total += len(s["operacoes"])
        for p in problemas:
            problemas_total.append(f"{s['slug']}: {p}")
        shutil.copyfile(arq, AQUI / arq.name)
    shutil.rmtree(BUILD, ignore_errors=True)

    if quebrados:
        print("\n$ref sem destino na spec oficial (viraram objeto genérico):")
        for q in sorted(quebrados):
            print(f"  {q}")
    if cortes:
        print("\ngrupos circulares grandes cortados (referências internas viraram objeto genérico):")
        for tam, ex in cortes:
            print(f"  {tam} schemas (ex.: {', '.join(ex)})")
    print(f"\n{len(servicos)} serviços, {total} operações")
    for p in problemas_total:
        print(f"  PROBLEMA {p}")
    return 0 if ok and not problemas_total else 1


if __name__ == "__main__":
    sys.exit(main())
