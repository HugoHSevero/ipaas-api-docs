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
