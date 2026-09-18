#!/usr/bin/env python3
"""Normaliza a spec oficial da Meta (business-messaging-api) para o iPaaS.

A Meta publica a spec da WhatsApp Business Platform em
https://github.com/facebook/openapi (`business-messaging-api_v23.0.yaml`).
Ela é correta, mas tem quatro características que não sobrevivem ao
importador do iPaaS sem tratamento. Este script trata as quatro e recorta o
escopo, produzindo a spec fonte que o `slice_spec.py` consome.

1. `openapi: 3.1.0` -> `3.0.3`. As cinco specs já validadas no iPaaS são
   3.0.x e não há evidência de que o importador aceite 3.1. Na prática a
   spec da Meta não usa 3.1: zero `type` como lista, zero `$defs`, zero
   `webhooks`, e chega a usar `nullable`, que é keyword de 3.0. A única
   marca real de 3.1 é um `const`, convertido aqui para `enum`.

2. Todo path começa com `/{Version}/`, declarado como path parameter. Do
   jeito que vem, cada operação importada exigiria `Version` = `v23.0` como
   entrada em todo fluxo — ruído multiplicado por 113 operações. A versão vai
   para a URL do server e o parâmetro é removido.

3. As operações declaram `Authorization` (além de `User-Agent` e
   `Content-Type`) como parâmetro de header. No iPaaS quem injeta o Bearer é
   a conta cadastrada, então esses parâmetros só apareceriam como campos
   manuais duplicando a credencial. São removidos.

4. Treze operações não têm `tags` e o importador falha com HTTP 500 sem
   indicar a causa (seção 4 do playbook). Aqui toda operação recebe
   exatamente uma tag de domínio, o que também habilita o recorte por
   domínio do `slice_spec.py` — as 56 tags originais da Meta são granulares
   demais (a maioria com uma ou duas operações) e gerariam 56 serviços.

O recorte deixa de fora o que é de BSP/parceiro (Multi-Partner Solutions,
OBO Mobility, Pre-Verified Numbers, MM Lite, Solution Migration, Billing) e
o domínio Flows, que é grande e independente. Ver o README da pasta.

Uso:
    python3 tools/prepare_whatsapp.py <spec-origem.yaml|json> <destino.json>
"""

import json
import re
import sys
from pathlib import Path

METODOS = ("get", "post", "put", "delete", "patch", "head", "options")

VERSAO_GRAPH = "v23.0"
SERVIDOR = f"https://graph.facebook.com/{VERSAO_GRAPH}"

# Parâmetros de plumbing HTTP: a conta do iPaaS injeta o Bearer e o
# importador deriva o content-type do requestBody.
PARAMS_REMOVIDOS = {"Authorization", "User-Agent", "UserAgent", "Content-Type", "ContentType"}

DOMINIOS = {
    "mensagens": "Envio de mensagens, mídia, chamadas e histórico de conversas.",
    "templates": "Criação, consulta e remoção de templates de mensagem.",
    "numeros": "Números de telefone: registro, verificação, perfil, QR codes e bloqueios.",
    "contas": "WhatsApp Business Account: dados, usuários, agendamentos e webhooks.",
    "grupos": "Grupos do WhatsApp: criação, participantes, convites e solicitações.",
    "parceiros": "Tech Provider e Solution Partner: soluções multiparceiro, WABAs de clientes, "
                 "números pré-verificados, portfólio empresarial e linha de crédito.",
}

# Mapa explícito path -> domínio, aplicado ao path já sem o prefixo /{Version}.
# Mapear por path e não pelas tags da Meta porque as tags se contradizem entre
# métodos do mesmo path (ex.: GET /{WABA-ID}/message_templates é `Templates`,
# mas POST no mesmo path é `Flows,Send Flow`).
MAPA = {
    "/{Media-ID}": "mensagens",
    "/{Media-URL}": "mensagens",
    "/{Message-History-ID}/events": "mensagens",
    "/{Phone-Number-ID}/call_permissions": "mensagens",
    "/{Phone-Number-ID}/calls": "mensagens",
    "/{Phone-Number-ID}/marketing_messages": "mensagens",
    "/{Phone-Number-ID}/media": "mensagens",
    "/{Phone-Number-ID}/message_history": "mensagens",
    "/{Phone-Number-ID}/messages": "mensagens",
    "/{Phone-Number-ID}/messages_encrypted": "mensagens",

    "/{TEMPLATE_ID}": "templates",
    "/{WABA-ID}/message_templates": "templates",

    "/{Phone-Number-ID}": "numeros",
    "/{Phone-Number-ID}/block_users": "numeros",
    "/{Phone-Number-ID}/business_compliance_info": "numeros",
    "/{Phone-Number-ID}/conversational_automation": "numeros",
    "/{Phone-Number-ID}/deregister": "numeros",
    "/{Phone-Number-ID}/message_qrdls": "numeros",
    "/{Phone-Number-ID}/message_qrdls/{QR-Code-ID}": "numeros",
    "/{Phone-Number-ID}/official_business_account": "numeros",
    "/{Phone-Number-ID}/register": "numeros",
    "/{Phone-Number-ID}/request_code": "numeros",
    "/{Phone-Number-ID}/settings": "numeros",
    "/{Phone-Number-ID}/verify_code": "numeros",
    "/{Phone-Number-ID}/whatsapp_business_profile": "numeros",
    "/{Phone-Number-ID}/whatsapp_commerce_settings": "numeros",
    "/{WABA-ID}/phone_numbers": "numeros",
    "/{WhatsApp-Account-Number-ID}": "numeros",
    "/{WhatsApp-Business-Profile-ID}": "numeros",

    "/{Business-ID}/owned_whatsapp_business_accounts": "contas",
    "/{User-ID}/assigned_whatsapp_business_accounts": "contas",
    "/{WABA-ID}": "contas",
    "/{WABA-ID}/activities": "contas",
    "/{WABA-ID}/schedules": "contas",
    "/{WABA-ID}/subscribed_apps": "contas",
    "/{WhatsApp-Business-Account-ID}/assigned_users": "contas",

    "/{Phone-Number-ID}/groups": "grupos",
    "/{group_id}": "grupos",
    "/{group_id}/invite_link": "grupos",
    "/{group_id}/join_requests": "grupos",
    "/{group_id}/participants": "grupos",

    # Tech Provider / Solution Partner. Fora do recorte inicial por ser de
    # revenda, reincluído porque a **coexistência** (manter o número no app do
    # WhatsApp Business e na Cloud API ao mesmo tempo) só é onboardada por
    # Cadastro Incorporado, e isso exige ser Tech Provider. O fluxo de cadastro
    # em si é navegador, não REST; o que entra aqui é a gestão em volta dele.
    "/{Application-ID}/connected_client_businesses": "parceiros",
    "/{Application-ID}/whatsapp_business_solution": "parceiros",
    "/{Application-ID}/whatsapp_business_solutions": "parceiros",
    "/{Business-ID}": "parceiros",
    "/{Business-ID}/add_phone_numbers": "parceiros",
    "/{Business-ID}/client_whatsapp_business_accounts": "parceiros",
    "/{Business-ID}/extendedcredits": "parceiros",
    "/{Business-ID}/onboard_partners_to_mm_lite": "parceiros",
    "/{Business-ID}/preverified_numbers": "parceiros",
    "/{Business-ID}/share_preverified_numbers": "parceiros",
    "/{Migration-Intent-ID}": "parceiros",
    "/{OBO-Mobility-Intent-ID}": "parceiros",
    "/{Pre-Verified-Phone-Number-ID}": "parceiros",
    "/{Pre-Verified-Phone-Number-ID}/partners": "parceiros",
    "/{Pre-Verified-Phone-Number-ID}/request_code": "parceiros",
    "/{Pre-Verified-Phone-Number-ID}/verify_code": "parceiros",
    "/{Solution-ID}": "parceiros",
    "/{Solution-ID}/accept": "parceiros",
    "/{Solution-ID}/accept_deactivation_request": "parceiros",
    "/{Solution-ID}/access_token": "parceiros",
    "/{Solution-ID}/reject": "parceiros",
    "/{Solution-ID}/reject_deactivation_request": "parceiros",
    "/{Solution-ID}/send_deactivation_request": "parceiros",
    "/{WABA-Bot-ID}": "parceiros",
    "/{WABA-ID}/in_progress_onbehalf_request": "parceiros",
    "/{WABA-ID}/obo_mobility_intent": "parceiros",
    "/{WABA-ID}/set_obo_mobility_intent": "parceiros",
    "/{WABA-ID}/set_solution_migration_intent": "parceiros",
    "/{WABA-ID}/solutions": "parceiros",
}


# Campos que a API devolve e a spec oficial da Meta não documenta, observados em
# resposta real em 2026-09-18. O contrato importado é o que os fluxos de
# integração vão usar, então um campo ausente aqui é um campo que o fluxo não
# consegue mapear. Só acrescenta: nunca sobrescreve o que a Meta já declara.
#
# O localizador é um caminho de properties, onde `[]` desce para `items`:
#   "data[].components[]"  ->  properties.data.items.properties.components.items
STRING = {"type": "string"}
BOOLEANO = {"type": "boolean"}

COMPLEMENTOS_SCHEMAS = {
    "WhatsAppBusinessAccount": [
        ("", {"message_template_namespace": STRING}),
    ],
    "WhatsAppBusinessAccountPhoneNumbersConnection": [
        ("data[]", {
            "platform_type": STRING,
            "throughput": {"type": "object", "properties": {"level": STRING}},
        }),
    ],
}

_BOTAO_CARD = {
    "type": "object",
    "properties": {"type": STRING, "text": STRING, "url": STRING},
}
_COMPONENTE_CARD = {
    "type": "object",
    "properties": {
        "type": STRING,
        "format": STRING,
        "text": STRING,
        "buttons": {"type": "array", "items": _BOTAO_CARD},
    },
}

COMPLEMENTOS_PATHS = {
    "get /{WABA-ID}/message_templates": [
        ("data[]", {
            "parameter_format": STRING,
            "disable_ios_autofill": BOOLEANO,
            "is_primary_device_delivery_only": BOOLEANO,
        }),
        # templates de carrossel: cada card tem seus próprios componentes
        ("data[].components[]", {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "components": {"type": "array", "items": _COMPONENTE_CARD},
                    },
                },
            },
        }),
        ("data[].components[].buttons[]", {"url": STRING}),
    ],
}


def resolver_ref(spec, no):
    """Segue `$ref` até o schema concreto.

    Complementar um nó `{"$ref": ...}` acrescentando `properties` ao lado do
    `$ref` **apaga** as propriedades do schema referenciado: o dereference faz
    `{**resolvido, **irmãos}` e os irmãos vencem. O complemento tem que ser
    aplicado no destino do `$ref`.
    """
    visto = set()
    while isinstance(no, dict) and "$ref" in no:
        ref = no["$ref"]
        if ref in visto:
            raise ValueError(f"$ref circular ao resolver complemento: {ref}")
        visto.add(ref)
        alvo = spec
        for parte in ref[2:].split("/"):
            alvo = alvo[parte.replace("~1", "/").replace("~0", "~")]
        no = alvo
    return no


def navegar(spec, schema, localizador):
    """Desce por um caminho de properties; `[]` entra em items. None se não existir."""
    no = resolver_ref(spec, schema)
    if localizador:
        for parte in localizador.split("."):
            listas = parte.endswith("[]")
            nome = parte[:-2] if listas else parte
            no = (no.get("properties") or {}).get(nome)
            if no is None:
                return None
            no = resolver_ref(spec, no)
            if listas:
                no = no.get("items")
                if no is None:
                    return None
                no = resolver_ref(spec, no)
    return no


def complementar(spec, schema, patches, rotulo, avisos):
    for localizador, props in patches:
        alvo = navegar(spec, schema, localizador)
        if alvo is None:
            avisos.append(f"{rotulo}: localizador não encontrado: {localizador or '(raiz)'}")
            continue
        if "allOf" in alvo:
            # mesmo problema do $ref: `properties` irmão de `allOf` vence a
            # mesclagem e descarta os membros. Entra como um membro a mais.
            alvo["allOf"].append({"type": "object", "properties": json.loads(json.dumps(props))})
            continue
        destino = alvo.setdefault("properties", {})
        for nome, sub in props.items():
            if nome in destino:
                continue  # a Meta já documenta: não sobrescreve
            destino[nome] = json.loads(json.dumps(sub))


# `items` que a spec da Meta esquece de declarar. Um `type: array` sem `items`
# faz o importador do iPaaS responder HTTP 200 e não criar recurso nenhum — uma
# ocorrência zera a spec inteira, sem mensagem de erro. Isolado por bissecção:
# era isso que derrubava as 11 operações do serviço de mensagens.
#
# A chave é o nome da propriedade cujo array está sem `items`.
ITEMS_FALTANDO = {
    # parâmetros de componente de template (POST /messages e /marketing_messages).
    # Forma confirmada em envio real: {"type": "text", "text": "..."}.
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["text", "currency", "date_time", "image", "document",
                         "video", "location", "button", "payload"],
            },
            "parameter_name": STRING,
            "text": STRING,
            "payload": STRING,
            "currency": {
                "type": "object",
                "properties": {
                    "fallback_value": STRING,
                    "code": STRING,
                    "amount_1000": {"type": "integer"},
                },
            },
            "date_time": {"type": "object", "properties": {"fallback_value": STRING}},
            "image": {"type": "object", "properties": {"id": STRING, "link": STRING}},
            "document": {
                "type": "object",
                "properties": {"id": STRING, "link": STRING, "filename": STRING},
            },
            "video": {"type": "object", "properties": {"id": STRING, "link": STRING}},
        },
    },
}


def preencher_items(no, nome_prop=None, aplicados=None, sem_mapa=None):
    """Declara `items` em todo `type: array` que não tem."""
    if aplicados is None:
        aplicados, sem_mapa = [], []
    if isinstance(no, dict):
        if no.get("type") == "array" and "items" not in no:
            modelo = ITEMS_FALTANDO.get(nome_prop)
            if modelo is None:
                no["items"] = {"type": "object"}
                sem_mapa.append(nome_prop or "(sem nome)")
            else:
                no["items"] = json.loads(json.dumps(modelo))
                aplicados.append(nome_prop)
        for k, v in no.items():
            if k == "properties" and isinstance(v, dict):
                for pn, pv in v.items():
                    preencher_items(pv, pn, aplicados, sem_mapa)
            else:
                preencher_items(v, nome_prop, aplicados, sem_mapa)
    elif isinstance(no, list):
        for v in no:
            preencher_items(v, nome_prop, aplicados, sem_mapa)
    return aplicados, sem_mapa


def limpar_parametros(lista):
    """Remove Version e os parâmetros de plumbing HTTP."""
    saida = []
    for p in lista or []:
        if "$ref" in p:
            nome = p["$ref"].rsplit("/", 1)[-1]
            if nome == "Version" or nome in PARAMS_REMOVIDOS:
                continue
        elif p.get("name") in PARAMS_REMOVIDOS or (
            p.get("name") == "Version" and p.get("in") == "path"
        ):
            continue
        saida.append(p)
    return saida


def const_para_enum(no):
    """`const` é 3.1; o equivalente em 3.0 é um enum de um item."""
    if isinstance(no, dict):
        if "const" in no:
            no["enum"] = [no.pop("const")]
        return {k: const_para_enum(v) for k, v in no.items()}
    if isinstance(no, list):
        return [const_para_enum(i) for i in no]
    return no


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    origem, destino = sys.argv[1], sys.argv[2]

    texto = Path(origem).read_text(encoding="utf-8")
    if origem.endswith((".yaml", ".yml")):
        import yaml
        spec = yaml.safe_load(texto)
    else:
        spec = json.loads(texto)

    spec["openapi"] = "3.0.3"
    spec["servers"] = [{"url": SERVIDOR, "description": f"WhatsApp Business Cloud API ({VERSAO_GRAPH})"}]
    spec["info"]["title"] = "WhatsApp Business Cloud API"
    spec["tags"] = [{"name": n, "description": d} for n, d in sorted(DOMINIOS.items())]

    paths_novos = {}
    descartados = []
    contagem = {}

    for caminho, item in spec.get("paths", {}).items():
        curto = re.sub(r"^/\{Version\}", "", caminho)
        dominio = MAPA.get(curto)
        if dominio is None:
            descartados.append((curto, len([m for m in item if m in METODOS])))
            continue

        novo = {}
        for chave, valor in item.items():
            if chave == "parameters":
                limpos = limpar_parametros(valor)
                if limpos:
                    novo["parameters"] = limpos
            elif chave in METODOS:
                op = dict(valor)
                op["tags"] = [dominio]
                limpos = limpar_parametros(op.get("parameters"))
                if limpos:
                    op["parameters"] = limpos
                else:
                    op.pop("parameters", None)
                novo[chave] = op
                contagem[dominio] = contagem.get(dominio, 0) + 1
            else:
                novo[chave] = valor
        paths_novos[curto] = novo

    spec["paths"] = paths_novos

    avisos = []
    for nome, patches in COMPLEMENTOS_SCHEMAS.items():
        alvo = (spec.get("components") or {}).get("schemas", {}).get(nome)
        if alvo is None:
            avisos.append(f"schema não encontrado: {nome}")
            continue
        complementar(spec, alvo, patches, nome, avisos)

    for chave, patches in COMPLEMENTOS_PATHS.items():
        metodo, caminho = chave.split(" ", 1)
        op = (paths_novos.get(caminho) or {}).get(metodo)
        if op is None:
            avisos.append(f"operação não encontrada: {chave}")
            continue
        alvo = (
            op.get("responses", {}).get("200", {})
            .get("content", {}).get("application/json", {}).get("schema")
        )
        if alvo is None:
            avisos.append(f"{chave}: sem schema de resposta 200 em application/json")
            continue
        complementar(spec, alvo, patches, chave, avisos)

    spec = const_para_enum(spec)
    aplicados, sem_mapa = preencher_items(spec)

    Path(destino).write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"{origem} -> {destino}")
    print(f"  openapi 3.1.0 -> {spec['openapi']}, server {SERVIDOR}")
    print(f"  {len(paths_novos)} paths mantidos, {len(descartados)} descartados")
    print("  operações por domínio:")
    for d in sorted(contagem):
        print(f"    {contagem[d]:4d}  {d}")
    print(f"  total mantido: {sum(contagem.values())}")

    faltando = [d for d in DOMINIOS if d not in contagem]
    if faltando:
        print(f"  ERRO domínios sem nenhuma operação: {', '.join(faltando)}")
        return 1
    if avisos:
        for a in avisos:
            print(f"  ERRO complemento não aplicado: {a}")
        return 1
    n = sum(len(p) for p in COMPLEMENTOS_SCHEMAS.values()) + sum(
        len(p) for p in COMPLEMENTOS_PATHS.values()
    )
    print(f"  {n} complementos de schema aplicados (campos observados em resposta real)")
    if aplicados:
        print(f"  items declarados com schema conhecido: {', '.join(sorted(set(aplicados)))}")
    if sem_mapa:
        print(f"  items preenchidos com 'object' genérico (sem mapa): {', '.join(sorted(set(sem_mapa)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
