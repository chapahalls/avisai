"""Página do recebedor (plano B) pega canal, uid e token pela API."""


async def test_dada_ligacao_em_andamento_entao_pagina_recebe_token(client, container):
    lig = (await client.post("/rotas/1/ligar-recebedor", json={"motivo": "cco_sem_resposta"})).json()
    r = await client.get(f"/ligacoes/{lig['id']}")
    assert r.status_code == 200
    d = r.json()
    assert d["canal"] == f"avisai-recebedor-{lig['id']}"
    assert d["uid"] == 3001
    assert d["token"].startswith("007")
    atual = (await client.get("/ligacoes/atual/recebedor")).json()
    assert atual["id"] == lig["id"]


async def test_sem_ligacao_em_andamento_atual_e_nula(client):
    assert (await client.get("/ligacoes/atual/recebedor")).json() == {"ligacao": None}
