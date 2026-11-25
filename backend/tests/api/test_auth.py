"""Dado/quando/então: token real no SSO, papel cco nas ações da central e limite de ligações manuais."""
import time

import jwt
import pytest

from app.infra import auth

NOVA_ROTA = {
    "origem": {"nome": "CD Jundiaí", "lat": -23.18, "lng": -46.88},
    "destino": {"nome": "Atacado Campinas", "lat": -22.90, "lng": -47.06},
    "recebedor": {"empresa": "Atacado Campinas", "nome": "Paula", "telefone_e164": "+5519900000002"},
    "carga_t": 20, "placa": "ABC1D23", "nota_fiscal": "000.600.111",
}


async def _token(client, email: str) -> str:
    r = await client.post("/auth/sso", json={"email": email})
    assert r.status_code == 200
    return r.json()["token"]


async def _email_por_papel(client, papel: str) -> str:
    return (await client.get("/usuarios", params={"role": papel})).json()[0]["email"]


async def test_sso_devolve_jwt_assinado_com_papel_e_validade(client, container):
    perfil = (await client.get("/usuarios", params={"role": "cco"})).json()[0]
    token = await _token(client, perfil["email"])
    claims = auth.validar(container.settings, token)
    assert claims["role"] == "cco" and claims["email"] == perfil["email"] and claims["sub"] == perfil["id"]
    assert claims["exp"] - claims["iat"] == int(container.settings.auth_token_validade_h * 3600)


async def test_token_adulterado_ou_expirado_e_rejeitado(container):
    s = container.settings
    perfil = {"id": "1", "email": "cco@rotasul.test", "role": "cco", "driverId": None}
    valido = auth.emitir(s, perfil)
    falso = jwt.encode({**jwt.decode(valido, options={"verify_signature": False}), "role": "cco"}, "outro", algorithm="HS256")
    expirado = auth.emitir(s, perfil, agora=time.time() - 10 * 24 * 3600)
    for token in [falso, expirado, "lixo"]:
        with pytest.raises(auth.TokenInvalido):
            auth.validar(s, token)


async def test_com_auth_obrigatoria_publicar_rota_exige_cco(client, container):
    container.settings.auth_obrigatoria = True
    sem = await client.post("/rotas", json=NOVA_ROTA)
    assert sem.status_code == 401

    motorista = await _token(client, await _email_por_papel(client, "driver"))
    proibido = await client.post("/rotas", json=NOVA_ROTA, headers={"Authorization": f"Bearer {motorista}"})
    assert proibido.status_code == 403

    cco = await _token(client, await _email_por_papel(client, "cco"))
    ok = await client.post("/rotas", json=NOVA_ROTA, headers={"Authorization": f"Bearer {cco}"})
    assert ok.status_code == 200, ok.text


@pytest.mark.parametrize("metodo,caminho,corpo", [
    ("POST", "/tasks/1/confirmar", {}),
    ("POST", "/rotas/1/atribuir", {"motorista_id": 1}),
    ("POST", "/motoristas", {"nome": "X", "telefone_e164": "+5511900000099", "email": "x@rotasul.test"}),
    ("POST", "/cco/chamados/1/responder", {"resposta": "ok"}),
    ("POST", "/cco/rotas/1/ligar", {"destino": "operador", "motivo": "teste"}),
])
async def test_acoes_da_central_bloqueadas_sem_token(client, container, metodo, caminho, corpo):
    container.settings.auth_obrigatoria = True
    r = await client.request(metodo, caminho, json=corpo)
    assert r.status_code == 401


async def test_leitura_e_app_do_motorista_continuam_abertos(client, container):
    container.settings.auth_obrigatoria = True
    assert (await client.get("/rotas")).status_code == 200
    assert (await client.get("/cco/estado")).status_code == 200


async def test_sem_auth_obrigatoria_token_invalido_ainda_e_401(client, container):
    r = await client.post("/rotas", json=NOVA_ROTA, headers={"Authorization": "Bearer lixo"})
    assert r.status_code == 401


async def test_limite_de_ligacoes_manuais_por_rota(client, container, rota_id):
    container.settings.ligacoes_manuais_max = 2
    codigos = [(await client.post(f"/rotas/{rota_id}/ligar-recebedor", json={})).status_code for _ in range(3)]
    assert codigos[:2] != [429, 429] and codigos[2] == 429


def test_janela_do_limite_libera_depois_do_tempo():
    lim = auth.LimiteChamadas()
    assert lim.permitir("r", 1, 60, agora=0)
    assert not lim.permitir("r", 1, 60, agora=30)
    assert lim.permitir("r", 1, 60, agora=61)
    assert lim.permitir("outra", 1, 60, agora=30)


async def test_llm_exige_segredo_exato(client, container):
    container.settings.llm_shared_secret = "segredo"
    for cabecalho in ["", "Bearer errado", "Bearer segredo-mais-longo", "segredo-com-prefixo segredo"]:
        r = await client.post("/v1/chat/completions", json={"messages": []}, headers={"Authorization": cabecalho})
        assert r.status_code == 401, cabecalho
