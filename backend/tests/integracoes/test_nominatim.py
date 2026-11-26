"""Adaptador Nominatim com transporte simulado: contrato da consulta, tradução, cache e erros explícitos."""
import httpx
import pytest

from app.infra.settings import Settings
from app.integracoes.nominatim import GeocodificacaoErro, NominatimGeocodificador

RESPOSTA = [
    {"place_id": 9911, "osm_type": "way", "osm_id": 4455, "lat": "-23.5015", "lon": "-47.4526",
     "display_name": "Avenida do Atacado, Sorocaba, São Paulo, Brasil", "type": "road"},
    {"place_id": 9912, "osm_type": "node", "osm_id": 77, "lat": "-23.50", "lon": "-47.45",
     "display_name": "Atacado Sorocaba, Sorocaba", "type": "shop"},
]


def _geo(handler) -> tuple[NominatimGeocodificador, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def registrar(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return handler(request)

    s = Settings(geocodificacao_url="https://geo.test/", geocodificacao_intervalo_s=0,
                 geocodificacao_user_agent="AvisAI-teste/1")
    return NominatimGeocodificador(s, transporte=httpx.MockTransport(registrar)), pedidos


async def test_consulta_e_traducao():
    geo, pedidos = _geo(lambda r: httpx.Response(200, json=RESPOSTA))
    resultados = await geo.buscar("Atacado Sorocaba", 3)
    assert resultados == [
        {"id": "W4455", "endereco": "Avenida do Atacado, Sorocaba, São Paulo, Brasil", "lat": -23.5015, "lng": -47.4526,
         "tipo": "road"},
        {"id": "N77", "endereco": "Atacado Sorocaba, Sorocaba", "lat": -23.5, "lng": -47.45, "tipo": "shop"},
    ]
    p = pedidos[0]
    assert p.url.host == "geo.test" and p.url.path == "/search"
    assert p.url.params["q"] == "Atacado Sorocaba" and p.url.params["limit"] == "3"
    assert p.url.params["countrycodes"] == "br" and p.url.params["format"] == "jsonv2"
    assert p.headers["user-agent"] == "AvisAI-teste/1"


async def test_cache_evita_segunda_consulta_igual():
    geo, pedidos = _geo(lambda r: httpx.Response(200, json=RESPOSTA))
    await geo.buscar("Atacado Sorocaba")
    await geo.buscar("  atacado   SOROCABA ")
    assert len(pedidos) == 1


@pytest.mark.parametrize("resposta", [
    httpx.Response(503, text="manutenção"),
    httpx.Response(429, text="limite"),
    httpx.Response(200, text="<html>"),
    httpx.Response(200, json=[{"place_id": 1, "lat": "x", "lon": "1", "display_name": "ruim"}]),
    httpx.Response(200, json=[{"place_id": 1, "lat": "-123", "lon": "1", "display_name": "fora"}]),
])
async def test_erro_do_provedor_e_explicito_e_nao_entra_no_cache(resposta):
    geo, pedidos = _geo(lambda r: resposta)
    with pytest.raises(GeocodificacaoErro):
        await geo.buscar("Sorocaba")
    with pytest.raises(GeocodificacaoErro):
        await geo.buscar("Sorocaba")
    assert len(pedidos) == 2


async def test_falha_de_rede_vira_erro_de_geocodificacao():
    def cair(request):
        raise httpx.ConnectTimeout("sem rede", request=request)

    geo, _ = _geo(cair)
    with pytest.raises(GeocodificacaoErro, match="ConnectTimeout"):
        await geo.buscar("Sorocaba")
