#!/usr/bin/env python3
"""Gera as specs fonte do TOTVS Assinatura Eletrônica (TAE) a partir dos swaggers oficiais.

O TAE publica três APIs, cada uma com um swagger.json por versão:

    https://totvssign.staging.totvs.app/<api>/swagger/v<N>/swagger.json

    identityintegration  v1..v3   -> openapi-identidade.json
    documents            v1..v4   -> openapi-documentos.json
    signintegration      v1..v3   -> openapi-assinaturas.json
    contact              v1..v2   -> openapi-contatos.json
    webhooks             v1       -> openapi-webhooks.json
    deadletter           v1       -> openapi-deadletter.json

Transformações aplicadas (e só estas):

- junta as versões de cada API num arquivo só (um serviço por API no iPaaS);
- prefixa os paths com o segmento da API (`/documents/v1/...`), porque o
  `servers` oficial é relativo (`/documents`). Assim um único ambiente com
  base `https://totvssign.totvs.app` atende os seis serviços;
- renomeia schemas com o mesmo nome e conteúdo diferente entre versões
  (sufixo `_vN`), para a junção não sobrescrever nada;
- preenche `summary` vazio com `operationId` ou `MÉTODO path`, porque o nome
  do recurso no iPaaS vem do summary.

Uso:
    python3 tae/gerar.py            # baixa do staging
    python3 tae/gerar.py <pasta>    # usa <pasta>/<api>-v<N>.json já baixados
    python3 tools/dereference.py tae
"""

import json
import sys
import urllib.request
from pathlib import Path

HOST = "https://totvssign.staging.totvs.app"
METODOS = ("get", "post", "put", "delete", "patch")
APIS = [
    ("identityintegration", [1, 2, 3], "identidade", "TOTVS Assinatura Eletrônica - Identidade"),
    ("documents", [1, 2, 3, 4], "documentos", "TOTVS Assinatura Eletrônica - Documentos"),
    ("signintegration", [1, 2, 3], "assinaturas", "TOTVS Assinatura Eletrônica - Assinaturas"),
    ("contact", [1, 2], "contatos", "TOTVS Assinatura Eletrônica - Contatos"),
    ("webhooks", [1], "webhooks", "TOTVS Assinatura Eletrônica - Webhooks"),
    ("deadletter", [1], "deadletter", "TOTVS Assinatura Eletrônica - Dead Letter"),
]
PASTA = Path(__file__).resolve().parent


def carregar(api, versao, origem):
    if origem:
        return json.loads((Path(origem) / f"{api}-v{versao}.json").read_text(encoding="utf-8"))
    url = f"{HOST}/{api}/swagger/v{versao}/swagger.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def renomear_refs(no, mapa):
    if isinstance(no, dict):
        out = {}
        for k, v in no.items():
            if k == "$ref" and isinstance(v, str) and v in mapa:
                out[k] = mapa[v]
            else:
                out[k] = renomear_refs(v, mapa)
        return out
    if isinstance(no, list):
        return [renomear_refs(i, mapa) for i in no]
    return no


def juntar(api, versoes, titulo, origem):
    paths, schemas, tags, seguranca = {}, {}, {}, {}
    renomeados = []
    for v in versoes:
        spec = carregar(api, v, origem)
        prefixo = "/" + spec.get("servers", [{}])[0].get("url", f"/{api}").strip("/")
        comps = (spec.get("components") or {}).get("schemas") or {}

        mapa = {}
        for nome, sch in comps.items():
            if nome in schemas and schemas[nome] != sch:
                novo = f"{nome}_v{v}"
                mapa[f"#/components/schemas/{nome}"] = f"#/components/schemas/{novo}"
                renomeados.append(f"{nome} -> {novo}")
        spec = renomear_refs(spec, mapa)
        for nome, sch in ((spec.get("components") or {}).get("schemas") or {}).items():
            schemas[mapa.get(f"#/components/schemas/{nome}", f"#/components/schemas/{nome}").rsplit("/", 1)[1]] = sch

        seguranca.update((spec.get("components") or {}).get("securitySchemes") or {})
        for t in spec.get("tags") or []:
            tags.setdefault(t["name"], t)

        for caminho, item in spec.get("paths", {}).items():
            destino = prefixo + caminho
            if destino in paths:
                raise SystemExit(f"path duplicado entre versões: {destino}")
            for m, op in item.items():
                if m not in METODOS:
                    continue
                for t in op.get("tags") or []:
                    tags.setdefault(t, {"name": t})
                if not (op.get("summary") or "").strip():
                    op["summary"] = op.get("operationId") or f"{m.upper()} {destino}"
            paths[destino] = item

    spec = {
        "openapi": "3.0.1",
        "info": {"title": titulo, "version": "+".join(f"v{v}" for v in versoes),
                 "description": f"Fonte: {HOST}/{api}/swagger/ (versões {', '.join(f'v{v}' for v in versoes)})."},
        "servers": [{"url": "https://totvssign.totvs.app", "description": "Produção"},
                    {"url": HOST, "description": "Homologação"}],
        "tags": list(tags.values()),
        "paths": paths,
        "components": {"schemas": schemas, "securitySchemes": seguranca},
        "security": [{n: []} for n in seguranca],
    }
    return spec, renomeados


def main():
    origem = sys.argv[1] if len(sys.argv) > 1 else None
    for api, versoes, slug, titulo in APIS:
        spec, renomeados = juntar(api, versoes, titulo, origem)
        arq = PASTA / f"openapi-{slug}.json"
        arq.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ops = sum(len([m for m in i if m in METODOS]) for i in spec["paths"].values())
        print(f"{arq.name}: {ops} operações, {len(spec['components']['schemas'])} schemas")
        for r in renomeados:
            print(f"    schema renomeado: {r}")


if __name__ == "__main__":
    main()
