#!/usr/bin/env python3
"""Gera o flow JSON do diagrama de validacao do Cloudinary e imprime o corpo
pronto para o POST de sketch/publish. Andaime de validacao — removido depois."""
import json

APP = "3230d94e-64ce-45d2-85a0-2f937d0c045b"
ENV = "bae51566-ae3f-4d77-9e70-71e1af049e67"
ACC = "65090553-82ea-40d7-9be0-5cb92cc08c36"
CLOUD = "z1hdjfbz"

SVC_META = "ed936eb3-ce24-4e9a-96f3-741ddb80cca6"
SVC_UPLOAD = "cc428be6-51da-4252-8b02-0164d8a1e1e9"
SVC_REC = "9b8ce73b-a9ec-4e5d-bc3b-8305265e1299"

R_PING = "314175c8-b601-4f0d-a936-9ee3b4fb8b45"
R_UPLOAD = "b95f8e9c-6742-4c85-8c10-8ce9b59d5d8b"
R_DETAIL = "7c8bfe90-b432-47df-8010-6f826a887b74"

RESPONSE_ORIG = "76c0da1d-ca69-4381-9124-d5d40d9eb106-synchronous-webhook-response"

# PNG 1x1 transparente em Data URI
B64 = ("data:image/png;base64,"
       "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
URL_IMG = "https://res.cloudinary.com/demo/image/upload/sample.jpg"

TOP = 9000
LEFT0 = 9000
DX = 280


def pos(i):
    return {"top": f"{TOP + (13 if i == 0 else 0)}px", "left": f"{LEFT0 + i * DX}px"}


def rest_step(sid, name, label, service_id, resource_id, inpath, inbody=None, inquery=None, nxt=None, prev=None):
    conf = {
        "name": label,
        "environmentId": ENV,
        "applicationService": service_id,
        "accountId": ACC,
        "inPath": inpath,
        "inQuery": inquery or {},
        "inHeader": {},
    }
    if inbody is not None:
        conf["inBody"] = inbody
    return {
        "id": sid, "name": name, "type": "REST", "label": label,
        "isCustom": True, "isDropped": True,
        "positions": None,
        "serviceId": service_id, "componentId": APP,
        "componentResourceId": resource_id, "originalComponentId": APP,
        "configurations": conf,
        "connections": {"next": nxt or [], "previous": prev or [], "finalConnections": []},
    }


# offsets de conexao
def out_pt(p, t):
    if t == "WEBHOOK_SYNC":
        return (p["left"] + 66, p["top"] + 32)
    if t == "REST":
        return (p["left"] + 79, p["top"] + 45)
    return (p["left"], p["top"])


def in_pt(p, t):
    if t == "REST":
        return (p["left"] - 9, p["top"] + 45)
    if t == "WEBHOOK_RESPONSE":
        return (p["left"] - 8, p["top"] + 32)
    return (p["left"], p["top"])


def px(p):
    return {"top": int(p["top"][:-2]), "left": int(p["left"][:-2])}


def final_conn(a_id, b_id, a_pos, a_type, b_pos, b_type):
    sx, sy = out_pt(px(a_pos), a_type)
    ex, ey = in_pt(px(b_pos), b_type)
    mx = (sx + ex) // 2
    path = f"M {sx} {sy}\n    L {sx-32} {sy} L {sx} {sy}\n    L {mx} {sy} L {mx} {ey}\n    T {ex} {ey}"
    return {"connectionId": f"{a_id}#{b_id}", "connectionPath": path}


# monta os nos
start_id = "webhook-sync-trigger"
ids = [start_id, "id1", "id2", "id3", "id4", "id-synchronous-webhook-response5"]
types = ["WEBHOOK_SYNC", "REST", "REST", "REST", "REST", "WEBHOOK_RESPONSE"]
positions = [pos(i) for i in range(len(ids))]

activities = {}

# 0: trigger
activities[start_id] = {
    "id": start_id, "name": "Webhook síncrono", "type": "WEBHOOK_SYNC",
    "label": "Webhook síncrono", "positions": positions[0],
    "displayName": "backend.components.label.webhookSync", "configurations": {},
    "connections": {"next": ["id1"], "previous": [], "finalConnections": []},
}

# 1: ping
activities["id1"] = rest_step(
    "id1", "Cloudinary", "Ping", SVC_META, R_PING,
    {"cloud_name": CLOUD}, nxt=["id2"], prev=[start_id])
activities["id1"]["positions"] = positions[1]

# 2: upload por URL
activities["id2"] = rest_step(
    "id2", "Cloudinary", "Upload URL", SVC_UPLOAD, R_UPLOAD,
    {"cloud_name": CLOUD, "resource_type": "image"},
    inbody={"file": URL_IMG, "public_id": "ipaas_validacao_url"},
    nxt=["id3"], prev=["id1"])
activities["id2"]["positions"] = positions[2]

# 3: upload por base64
activities["id3"] = rest_step(
    "id3", "Cloudinary", "Upload base64", SVC_UPLOAD, R_UPLOAD,
    {"cloud_name": CLOUD, "resource_type": "image"},
    inbody={"file": B64, "public_id": "ipaas_validacao_b64"},
    nxt=["id4"], prev=["id2"])
activities["id3"]["positions"] = positions[3]

# 4: detalhe do asset criado por base64 (encadeia public_id)
activities["id4"] = rest_step(
    "id4", "Cloudinary", "Detalhe", SVC_REC, R_DETAIL,
    {"cloud_name": CLOUD, "resource_type": "image", "type": "upload", "public_id": "{{{id3.public_id}}}"},
    nxt=["id-synchronous-webhook-response5"], prev=["id3"])
activities["id4"]["positions"] = positions[4]

# 5: resposta sincrona agregando os payloads
resp_id = "id-synchronous-webhook-response5"
activities[resp_id] = {
    "id": resp_id, "name": "Resposta síncrona", "type": "WEBHOOK_RESPONSE",
    "label": "Resposta síncrona", "positions": positions[5],
    "displayName": "backend.components.label.syncResponse",
    "originalComponentId": RESPONSE_ORIG,
    "configurations": {"response": json.dumps({
        "ping": "{{{id1}}}",
        "upload_url": "{{{id2}}}",
        "upload_b64": "{{{id3}}}",
        "detalhe": "{{{id4}}}",
    }, ensure_ascii=False, indent=2)},
    "connections": {"next": [], "previous": ["id4"], "finalConnections": []},
}

# preenche finalConnections (setas) em cada no de saida
pairs = [(start_id, "id1"), ("id1", "id2"), ("id2", "id3"), ("id3", "id4"), ("id4", resp_id)]
idx = {i: n for i, n in enumerate(ids)}
tmap = {ids[i]: types[i] for i in range(len(ids))}
pmap = {ids[i]: positions[i] for i in range(len(ids))}
for a, b in pairs:
    fc = final_conn(a, b, pmap[a], tmap[a], pmap[b], tmap[b])
    activities[a]["connections"]["finalConnections"].append(fc)

flow = {"async": False, "start": start_id, "functions": {}, "activities": activities}

body = {
    "name": "Valida Cloudinary",
    "description": "Validacao do app Cloudinary: ping, upload por URL, upload por base64 e detalhe do asset.",
    "flow": flow,
    "icons": [],
    "dynamicIcons": True,
    "descriptionEdit": "",
}

import pathlib
pathlib.Path("cloudinary/_flow_body.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
print("ok, steps:", list(flow["activities"].keys()))
