#!/usr/bin/env python3
"""Monta os serviços do Calendly a partir das specs por domínio do apis.io.

Cada arquivo em _src/*.yml é um OpenAPI 3.1.0 independente (um domínio da API
v2 do Calendly, espelhado em github.com/api-evangelist/calendly). Aqui:

  1. agrupo os domínios em 4 serviços de negócio coerentes;
  2. mesclo paths + components de cada grupo num único documento;
  3. rebaixo 3.1.0 -> 3.0.3 (o importador do iPaaS só foi validado com OAS 3.0);
  4. gravo openapi-<slug>.json (fonte para o tools/dereference.py).

Saneamento 3.1 -> 3.0 aplicado: type como lista com "null" vira type escalar +
nullable; `const` vira enum de um item; `examples` (plural) em schema é removido;
`exclusiveMinimum`/`exclusiveMaximum` numéricos (3.1) viram booleanos (3.0).
"""
import glob
import json
import os

import yaml

D = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(D, "_src")

# serviço -> (slug, [nomes de arquivo em _src, sem .yml])
SERVICOS = {
    "Usuários e Organização": ("usuarios-organizacao",
        ["users", "organizations", "groups", "activity-log", "data-compliance"]),
    "Agendamentos": ("agendamentos",
        ["scheduled-events", "invitees"]),
    "Tipos de Evento e Disponibilidade": ("tipos-evento-disponibilidade",
        ["event-types", "availability", "shares"]),
    "Roteamento e Webhooks": ("roteamento-webhooks",
        ["routing-forms", "webhook-subscriptions"]),
}


def sanear_31(no):
    """Rebaixa construções OpenAPI 3.1 para 3.0 in-place, recursivamente."""
    if isinstance(no, dict):
        # type: ["string","null"] -> type: "string" + nullable: true
        t = no.get("type")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            if "null" in t:
                no["nullable"] = True
            no["type"] = non_null[0] if non_null else "string"
        # const -> enum
        if "const" in no:
            no["enum"] = [no.pop("const")]
        # examples (plural) em schema não existe em 3.0
        if "examples" in no and "properties" not in no and "$ref" not in no:
            no.pop("examples", None)
        # exclusiveMinimum/Maximum numéricos (3.1) -> booleano (3.0)
        for lim, base in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
            v = no.get(lim)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                no[base] = v
                no[lim] = True
        for v in no.values():
            sanear_31(v)
    elif isinstance(no, list):
        for i in no:
            sanear_31(i)


def merge(grupo_arquivos):
    paths = {}
    comp = {"schemas": {}, "responses": {}, "parameters": {}, "securitySchemes": {}}
    tags = {}
    servers = None
    for nome in grupo_arquivos:
        spec = yaml.safe_load(open(os.path.join(SRC, nome + ".yml"), encoding="utf-8"))
        servers = servers or spec.get("servers")
        for t in spec.get("tags", []):
            tags[t["name"]] = t
        for p, item in (spec.get("paths") or {}).items():
            if p in paths:
                paths[p].update(item)   # domínios distintos raramente colidem no path
            else:
                paths[p] = item
        for sec, bloco in (spec.get("components") or {}).items():
            for k, v in bloco.items():
                if k in comp[sec] and json.dumps(comp[sec][k], sort_keys=True) != json.dumps(v, sort_keys=True):
                    # colisão de nome com conteúdo diferente entre domínios
                    raise SystemExit(f"COLISAO em components.{sec}.{k} entre {grupo_arquivos}")
                comp[sec][k] = v
    doc = {
        "openapi": "3.0.3",
        "info": {"title": "Calendly", "version": "2.0.0"},
        "servers": servers or [{"url": "https://api.calendly.com"}],
        "security": [{"bearerAuth": []}],
        "tags": list(tags.values()),
        "paths": paths,
        "components": {k: v for k, v in comp.items() if v},
    }
    sanear_31(doc)
    return doc


def main():
    linhas = []
    total = 0
    for nome, (slug, arquivos) in SERVICOS.items():
        doc = merge(arquivos)
        doc["info"]["title"] = f"Calendly - {nome}"
        out = os.path.join(D, f"openapi-{slug}.json")
        json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(out, "a", encoding="utf-8").write("\n")
        ops = sum(1 for m in doc["paths"].values() for k in m
                  if k in ("get", "post", "put", "delete", "patch"))
        total += ops
        linhas.append(f"{nome}: {ops} ops, {len(doc['components'].get('schemas', {}))} schemas -> openapi-{slug}.json")
    linhas.append(f"TOTAL: {total} ops")
    open(os.path.join(D, "_build.log"), "w", encoding="utf-8").write("\n".join(linhas))


main()
