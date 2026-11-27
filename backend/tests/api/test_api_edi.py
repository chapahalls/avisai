"""API do conector OCOREN: perfis de parceiro, download do arquivo e validação (docs/edi/ocoren-integracao.md).

Cenário da demo: rota com 11h40 de espera no destino -> 542/342 código "descarga" (001/01) com os campos
19-24 preenchidos (chegada e término da descarga); troca de parceiro gera o mesmo evento em OCOREN 3.1.
"""
from app.conectores.edi.layouts import ocoren_31, ocoren_50
from app.conectores.edi.motor import ler
from tests.api.test_publicacao_rota import NOVA


async def _parceiro_id(client, layout: str) -> int:
    parceiros = (await client.get("/edi/parceiros", params={"empresa_id": 1})).json()
    return next(p["id"] for p in parceiros if p["layout"] == layout)


async def _descarregar_com_espera(client, relogio, horas=11, minutos=40, rota_id=1):
    await client.post(f"/rotas/{rota_id}/chegada")
    relogio.avancar(hours=horas, minutes=minutos)
    await client.post(f"/rotas/{rota_id}/descarga")


def _linhas(resposta) -> list[str]:
    return [l for l in resposta.content.decode("cp1252").split("\r\n") if l]


async def test_seed_ja_cadastra_os_dois_perfis_de_parceiro(client):
    parceiros = (await client.get("/edi/parceiros", params={"empresa_id": 1})).json()
    assert {p["layout"] for p in parceiros} == {"ocoren-5.0", "ocoren-3.1"}


async def test_baixa_ocoren_5_0_com_11h40_de_espera_no_542(client, relogio):
    p50 = await _parceiro_id(client, "ocoren-5.0")
    await _descarregar_com_espera(client, relogio)

    r = await client.get("/rotas/1/ocoren", params={"parceiro": p50})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert 'filename="OCOREN_12345678000195_' in r.headers["content-disposition"]

    linhas = _linhas(r)
    assert [l[:3] for l in linhas] == ["000", "540", "541", "542"]
    assert all(len(l) == 250 for l in linhas)
    valores = ler(linhas[3], ocoren_50.REGISTRO_542)
    assert valores["codigo_ocorrencia"] == 1  # De-Para padrão: "descarga" -> 001
    assert valores["chegada_destino_data"] is not None and valores["chegada_destino_hora"] is not None
    assert valores["termino_descarga_data"] is not None and valores["termino_descarga_hora"] is not None
    # Campos 21-22/25-26: sem evento próprio de início de descarga/saída do destino hoje, ficam vazios.
    assert valores["inicio_descarga_data"] is None and valores["saida_destino_data"] is None


async def test_troca_de_parceiro_gera_ocoren_3_1_com_texto_livre(client, relogio):
    p31 = await _parceiro_id(client, "ocoren-3.1")
    await _descarregar_com_espera(client, relogio)

    r = await client.get("/rotas/1/ocoren", params={"parceiro": p31})
    assert r.status_code == 200, r.text
    linhas = _linhas(r)
    assert [l[:3] for l in linhas] == ["000", "340", "341", "342"]
    assert all(len(l) == 120 for l in linhas)
    valores = ler(linhas[3], ocoren_31.REGISTRO_342)
    assert valores["codigo_ocorrencia"] == 1  # De-Para da 3.1: "descarga" -> 01
    assert valores["texto_livre"] and "ESPERA" in valores["texto_livre"]


async def test_sem_chave_de_nfe_e_409(client):
    p50 = await _parceiro_id(client, "ocoren-5.0")
    nova = (await client.post("/rotas", json=NOVA)).json()  # /rotas não preenche nfe_chave
    r = await client.get(f"/rotas/{nova['id']}/ocoren", params={"parceiro": p50})
    assert r.status_code == 409
    assert "nfe" in r.text.lower()


async def test_rota_inexistente_e_404(client):
    p50 = await _parceiro_id(client, "ocoren-5.0")
    r = await client.get("/rotas/9999/ocoren", params={"parceiro": p50})
    assert r.status_code == 404


async def test_parceiro_inexistente_e_404(client):
    r = await client.get("/rotas/1/ocoren", params={"parceiro": 9999})
    assert r.status_code == 404


async def test_criar_listar_e_atualizar_parceiro(client):
    r = await client.post("/edi/parceiros", json={"empresa_id": 1, "nome": "Parceiro de teste", "layout": "ocoren-5.0"})
    assert r.status_code == 201, r.text
    parceiro = r.json()
    assert parceiro["codificacao"] == "cp1252" and parceiro["transporte"] == "download"

    listados = (await client.get("/edi/parceiros", params={"empresa_id": 1})).json()
    assert any(p["id"] == parceiro["id"] for p in listados)

    r2 = await client.patch(f"/edi/parceiros/{parceiro['id']}",
                            json={"layout": "ocoren-3.1", "depara": {"descarga": "99"}})
    assert r2.status_code == 200, r2.text
    assert r2.json()["layout"] == "ocoren-3.1" and r2.json()["depara"] == {"descarga": "99"}


async def test_criar_parceiro_com_layout_fora_do_contrato_e_422(client):
    r = await client.post("/edi/parceiros", json={"empresa_id": 1, "nome": "X", "layout": "ocoren-9.9"})
    assert r.status_code == 422


async def test_atualizar_parceiro_inexistente_e_404(client):
    r = await client.patch("/edi/parceiros/9999", json={"nome": "Y"})
    assert r.status_code == 404


async def test_validar_arquivo_gerado_nao_tem_erros(client, relogio):
    p50 = await _parceiro_id(client, "ocoren-5.0")
    await _descarregar_com_espera(client, relogio)
    gerado = await client.get("/rotas/1/ocoren", params={"parceiro": p50})

    r = await client.post("/edi/validar", params={"layout": "ocoren-5.0"},
                          files={"arquivo": ("OCOREN_teste.txt", gerado.content, "text/plain")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is True and corpo["erros"] == []
    assert {reg["registro"] for reg in corpo["registros"]} == {"000", "540", "541", "542"}


async def test_validar_arquivo_com_registro_desconhecido_reporta_erro_por_linha(client):
    ruim = b"XYZ" + b" " * 247 + b"\r\n"
    r = await client.post("/edi/validar", params={"layout": "ocoren-5.0"},
                          files={"arquivo": ("ruim.txt", ruim, "text/plain")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ok"] is False
    assert corpo["erros"][0]["linha"] == 1
    assert "desconhecido" in corpo["erros"][0]["erro"]
