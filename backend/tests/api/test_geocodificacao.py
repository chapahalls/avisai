"""Dado/quando/então: o CCO digita o endereço, escolhe um resultado e a rota guarda coordenada e vínculo."""
from app.infra.models import Rota
from app.integracoes.nominatim import GeocodificacaoErro
from tests.helpers import obter

BASE = {
    "recebedor": {"empresa": "Atacado Sorocaba", "nome": "Paula", "telefone_e164": "+5515900000003"},
    "carga_t": 18, "placa": "RST7C88",
}


async def test_busca_devolve_candidatos_com_atribuicao(client, fake_geocodificador):
    r = await client.get("/geocodificacao", params={"q": "  Sorocaba   atacado "})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["provedor"] == "fake" and corpo["atribuicao"]
    assert corpo["resultados"][0] == {"id": "W202", "endereco": "Avenida do Atacado, 2000, Sorocaba, SP",
                                      "lat": -23.5015, "lng": -47.4526, "tipo": "road"}
    assert fake_geocodificador.consultas[-1] == ("Sorocaba atacado", 5)


async def test_busca_sem_resultado_e_lista_vazia(client):
    r = await client.get("/geocodificacao", params={"q": "Manaus"})
    assert r.status_code == 200 and r.json()["resultados"] == []


async def test_consulta_curta_ou_limite_invalido_422(client):
    assert (await client.get("/geocodificacao", params={"q": "ab"})).status_code == 422
    assert (await client.get("/geocodificacao", params={"q": "    a    "})).status_code == 422
    assert (await client.get("/geocodificacao", params={"q": "Sorocaba", "limite": 50})).status_code == 422


async def test_sem_provedor_503_e_falha_do_provedor_502(client, container, fake_geocodificador):
    fake_geocodificador.falhar = GeocodificacaoErro("geocodificação indisponível: ConnectTimeout")
    falha = await client.get("/geocodificacao", params={"q": "Sorocaba"})
    assert falha.status_code == 502 and falha.json()["detail"]["erro"] == "geocodificacao"
    container.geocodificador = None
    r = await client.get("/geocodificacao", params={"q": "Sorocaba"})
    assert r.status_code == 503 and r.json()["detail"]["erro"] == "geocodificacao_nao_configurada"


async def test_com_auth_obrigatoria_busca_exige_cco(client, container):
    container.settings.auth_obrigatoria = True
    assert (await client.get("/geocodificacao", params={"q": "Sorocaba"})).status_code == 401


async def test_rota_guarda_endereco_coordenada_e_vinculo(client):
    nova = {
        **BASE,
        "origem": {"nome": "CD Jundiaí", "lat": -23.1857, "lng": -46.8978, "endereco": "Rua das Indústrias, 100",
                   "geo": {"fonte": "geocodificacao", "provedor": "fake", "id": "N101",
                           "endereco": "Rua das Indústrias, 100, Jundiaí, SP"}},
        "destino": {"nome": "Atacado Sorocaba", "lat": -23.5015, "lng": -47.4526},
    }
    r = await client.post("/rotas", json=nova)
    assert r.status_code == 200, r.text
    rota = obter(Rota, r.json()["id"])
    assert (rota.origem_lat, rota.origem_lng) == (-23.1857, -46.8978)
    assert rota.origem_endereco == "Rua das Indústrias, 100"
    assert rota.origem_geo == {"fonte": "geocodificacao", "provedor": "fake", "id": "N101",
                               "endereco": "Rua das Indústrias, 100, Jundiaí, SP"}
    # Sem vínculo informado, a coordenada conta como digitada.
    assert rota.destino_geo == {"fonte": "manual"} and rota.destino_endereco == ""
    assert r.json()["origem_geo"]["id"] == "N101"


async def test_coordenada_e_vinculo_validados(client):
    destino = {"nome": "Atacado Sorocaba", "lat": -23.5015, "lng": -47.4526}
    sem_lat = {**BASE, "origem": {"nome": "CD", "lng": -46.8}, "destino": destino}
    fora = {**BASE, "origem": {"nome": "CD", "lat": -123.0, "lng": -46.8}, "destino": destino}
    geo_sem_id = {**BASE, "origem": {"nome": "CD", "lat": -23.1, "lng": -46.8, "geo": {"fonte": "geocodificacao"}},
                  "destino": destino}
    for corpo in (sem_lat, fora, geo_sem_id):
        assert (await client.post("/rotas", json=corpo)).status_code == 422
