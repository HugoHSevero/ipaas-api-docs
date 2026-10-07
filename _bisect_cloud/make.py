#!/usr/bin/env python3
"""Gera specs de bisseccao a partir da openapi-recursos.ipaas.json real (ja dereferenciada).

Cada spec de saida contem um subconjunto das operacoes, preservando os schemas reais.
Assim isolamos qual operacao/schema zera a importacao, sem schemas de brinquedo.
"""
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REAL = AQUI.parent / "cloudinary" / "openapi-recursos.ipaas.json"

spec = json.loads(REAL.read_text(encoding="utf-8"))
paths = spec["paths"]

# achata em lista de (path, metodo, op)
ops = []
for p, metodos in paths.items():
    for m, op in metodos.items():
        if m in ("get", "post", "put", "delete", "patch"):
            ops.append((p, m, op))

print(f"{len(ops)} operacoes na spec real:")
for i, (p, m, _) in enumerate(ops):
    print(f"  [{i}] {m.upper()} {p}")


def monta(indices, nome):
    novo = {k: v for k, v in spec.items() if k != "paths"}
    novos_paths = {}
    for i in indices:
        p, m, op = ops[i]
        novos_paths.setdefault(p, {})[m] = op
    novo["paths"] = novos_paths
    novo["info"] = {**spec.get("info", {}), "title": f"Bisect {nome}"}
    destino = AQUI / f"real-{nome}.ipaas.json"
    destino.write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  real-{nome}: {len(indices)} ops -> {destino.name}")


n = len(ops)
meio = n // 2
print("\nGerando metades:")
monta(list(range(meio)), "h1")
monta(list(range(meio, n)), "h2")

# refino dentro de h2 (ops 3,4,5,6): uma spec por operacao isolada
print("\nGerando operacoes isoladas de h2:")
for i in (3, 4, 5, 6):
    _, m, _ = ops[i]
    monta([i], f"op{i}")

# variantes cirurgicas da op3 (DELETE) para isolar o campo culpado
import copy
print("\nGerando variantes da op3:")
_, _, op3 = ops[3]

def salva_variante(op, nome):
    novo = {k: v for k, v in spec.items() if k != "paths"}
    novo["paths"] = {"/{cloud_name}/resources/{resource_type}/{type}/{public_id}": {"delete": op}}
    novo["info"] = {**spec.get("info", {}), "title": f"Bisect {nome}"}
    (AQUI / f"{nome}.ipaas.json").write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {nome}.ipaas.json")

# v1: remove query params 'all' e 'invalidate' (boolean)
v1 = copy.deepcopy(op3)
v1["parameters"] = [p for p in v1["parameters"] if p["name"] not in ("all", "invalidate")]
salva_variante(v1, "op3-noboolq")

# v2: substitui objetos vazios da resposta por string
v2 = copy.deepcopy(op3)
props = v2["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
for k in ("deleted", "deleted_counts"):
    if k in props:
        props[k] = {"type": "string"}
salva_variante(v2, "op3-noemptyobj")

# v3: remove o parametro 'all' apenas (nome potencialmente reservado)
v3 = copy.deepcopy(op3)
v3["parameters"] = [p for p in v3["parameters"] if p["name"] != "all"]
salva_variante(v3, "op3-noall")
