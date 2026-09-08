#!/usr/bin/env python3
"""Gera as versões dereferenciadas das specs OpenAPI para importação no TOTVS iPaaS.

O importador do iPaaS não resolve `$ref`: um response que aponta para
`#/components/schemas/X` é importado como um único campo `response` do tipo
string, em vez dos campos do objeto. Este script resolve `$ref` e mescla
`allOf`, produzindo um `<nome>.ipaas.json` para cada `openapi*.json` da pasta.

Um app pode ter várias specs, uma por serviço:
    asaas/openapi-clientes.json    -> asaas/openapi-clientes.ipaas.json
    asaas/openapi-cobrancas.json   -> asaas/openapi-cobrancas.ipaas.json

Uso:
    python3 tools/dereference.py brasilapi
    python3 tools/dereference.py --all
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LIMITE_PROFUNDIDADE = 40
METODOS = ("get", "post", "put", "delete", "patch", "head", "options")

# $ref circulares truncados na dereferência da spec em processamento.
# Preenchido por dereferenciar(); lido e zerado por processar().
CICLOS_TRUNCADOS = set()


def resolver_ponteiro(spec, ref):
    """Resolve um JSON pointer local (#/a/b/c)."""
    if not ref.startswith("#/"):
        raise ValueError(f"$ref externo não suportado: {ref}")
    no = spec
    for parte in ref[2:].split("/"):
        parte = parte.replace("~1", "/").replace("~0", "~")
        if parte not in no:
            raise KeyError(f"$ref não resolve: {ref}")
        no = no[parte]
    return no


def mesclar_all_of(partes):
    """Mescla os membros de um allOf em um único schema."""
    resultado = {"type": "object", "properties": {}}
    requeridos = []
    for parte in partes:
        if parte.get("type") and parte["type"] != "object":
            # allOf sobre tipo escalar: usa o último não-objeto
            resultado = dict(parte)
            continue
        resultado["properties"].update(parte.get("properties", {}))
        requeridos.extend(parte.get("required", []))
        for chave in ("description", "example"):
            if chave in parte and chave not in resultado:
                resultado[chave] = parte[chave]
    if requeridos:
        resultado["required"] = sorted(set(requeridos))
    if not resultado.get("properties"):
        resultado.pop("properties", None)
    return resultado


def dereferenciar(no, spec, profundidade=0, vistos=None):
    if profundidade > LIMITE_PROFUNDIDADE:
        raise RecursionError("profundidade excedida: possível $ref circular")
    vistos = vistos or frozenset()

    if isinstance(no, dict):
        if "$ref" in no:
            ref = no["$ref"]
            if ref in vistos:
                # $ref circular (ex.: uma categoria que tem categorias filhas).
                # Não dá para inlinar uma árvore infinita, e como o importador
                # do iPaaS ignora $ref, o terminal correto é um objeto genérico:
                # preserva a estrutura acíclica e faz a recursão parar.
                nome = ref.split("/")[-1]
                CICLOS_TRUNCADOS.add(ref)
                return {"type": "object",
                        "description": f"Referência recursiva a {nome} "
                                       "(truncada; ver a spec fonte)"}
            alvo = resolver_ponteiro(spec, ref)
            resolvido = dereferenciar(alvo, spec, profundidade + 1, vistos | {ref})
            # preserva irmãos do $ref (ex.: description no ponto de uso)
            irmaos = {k: v for k, v in no.items() if k != "$ref"}
            if irmaos:
                resolvido = {**resolvido, **dereferenciar(irmaos, spec, profundidade + 1, vistos)}
            return resolvido

        if "allOf" in no:
            partes = [dereferenciar(p, spec, profundidade + 1, vistos) for p in no["allOf"]]
            mesclado = mesclar_all_of(partes)
            resto = {k: v for k, v in no.items() if k != "allOf"}
            return {**mesclado, **dereferenciar(resto, spec, profundidade + 1, vistos)}

        return {k: dereferenciar(v, spec, profundidade + 1, vistos) for k, v in no.items()}

    if isinstance(no, list):
        return [dereferenciar(i, spec, profundidade + 1, vistos) for i in no]

    return no


def validar_para_ipaas(spec):
    """Checa os requisitos que o importador do iPaaS impõe."""
    problemas = []
    for caminho, metodos in spec.get("paths", {}).items():
        for metodo, op in metodos.items():
            # o path item tambem carrega chaves que nao sao metodo (ex.: `parameters`)
            if metodo not in METODOS:
                continue
            alvo = f"{metodo.upper()} {caminho}"
            if not op.get("tags"):
                problemas.append(f"{alvo}: sem 'tags' — o import falha com HTTP 500")
            if not op.get("summary"):
                problemas.append(f"{alvo}: sem 'summary' — recurso fica sem nome descritivo")
    return problemas


def remover_esquemas_em_query(spec):
    """Remove securitySchemes com `in: query`, que quebram o importador do iPaaS.

    Verificado por bissecção: declarar um `securityScheme` de `type: apiKey`
    com `in: query` faz o `import-swagger` responder HTTP 500, mesmo que o
    esquema não seja referenciado em `security`. Com `in: header` importa
    normalmente. A autenticação em query continua funcionando em execução,
    porque quem injeta os parâmetros é a conta cadastrada no iPaaS.
    """
    esquemas = (spec.get("components") or {}).get("securitySchemes") or {}
    removidos = [n for n, e in esquemas.items() if isinstance(e, dict) and e.get("in") == "query"]
    if not removidos:
        return []

    for nome in removidos:
        esquemas.pop(nome)
    if not esquemas:
        (spec.get("components") or {}).pop("securitySchemes", None)

    requisitos = []
    for req in spec.get("security") or []:
        resto = {k: v for k, v in req.items() if k not in removidos}
        if resto:
            requisitos.append(resto)
    if requisitos:
        spec["security"] = requisitos
    else:
        spec.pop("security", None)

    return removidos


def processar(pasta: Path):
    """Processa todas as specs fonte da pasta (openapi.json e openapi-*.json)."""
    origens = sorted(
        f for f in pasta.glob("openapi*.json")
        if not f.name.endswith(".ipaas.json")
    )
    if not origens:
        print(f"  ignorado: {pasta.name} (sem openapi*.json)")
        return True

    ok = True
    for origem in origens:
        spec = json.loads(origem.read_text(encoding="utf-8"))
        problemas = validar_para_ipaas(spec)

        CICLOS_TRUNCADOS.clear()
        plano = dereferenciar(spec, spec)
        if CICLOS_TRUNCADOS:
            print(f"    $ref circular truncado: {', '.join(sorted(CICLOS_TRUNCADOS))}"
                  " (schema recursivo; virou objeto genérico no ponto do ciclo)")
        em_query = remover_esquemas_em_query(plano)
        if em_query:
            print(f"    securitySchemes em query removidos: {', '.join(em_query)}"
                  " (quebram o importador; a conta do iPaaS injeta os parâmetros)")
        # remove apenas o que foi embutido inline; securitySchemes descreve a
        # autenticação e nao e schema de dados, entao permanece
        componentes = plano.get("components") or {}
        seguranca = componentes.get("securitySchemes")
        if seguranca:
            plano["components"] = {"securitySchemes": seguranca}
        else:
            plano.pop("components", None)

        if json.dumps(plano, ensure_ascii=False).count('"$ref"'):
            problemas.append("ainda restam $ref após a dereferência")

        destino = pasta / (origem.stem + ".ipaas.json")
        destino.write_text(json.dumps(plano, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        ops = sum(
            len([m for m in metodos if m in ("get", "post", "put", "delete", "patch")])
            for metodos in plano.get("paths", {}).values()
        )
        kb = destino.stat().st_size // 1024
        print(f"  {pasta.name}/{origem.name}: {ops} operações -> {destino.name} ({kb} KB)")
        for p in problemas:
            print(f"    AVISO {p}")
        ok = ok and not problemas
    return ok


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    if args == ["--all"]:
        pastas = sorted(
            d for d in RAIZ.iterdir()
            if d.is_dir() and not d.name.startswith((".", "_")) and d.name != "tools"
        )
    else:
        pastas = [RAIZ / a for a in args]

    ok = True
    print("Gerando specs para o iPaaS:")
    for pasta in pastas:
        if not pasta.is_dir():
            print(f"  ERRO {pasta.name}: pasta não encontrada")
            ok = False
            continue
        ok = processar(pasta) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
