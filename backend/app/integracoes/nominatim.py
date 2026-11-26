"""Geocodificação pelo Nominatim (OpenStreetMap).

A instância pública aceita no máximo 1 requisição por segundo e exige um User-Agent que
identifique a aplicação; para volume maior, aponte GEOCODIFICACAO_URL para uma instância própria.
Sem fallback silencioso: falha de rede ou resposta inválida vira GeocodificacaoErro.
"""
import asyncio
import time
from collections import OrderedDict

import httpx


class GeocodificacaoErro(Exception):
    """O provedor falhou ou respondeu fora do contrato (HTTP 502 na API)."""


class NominatimGeocodificador:
    provedor = "nominatim"
    atribuicao = "© OpenStreetMap contributors"

    def __init__(self, settings, transporte: httpx.AsyncBaseTransport | None = None):
        self.url = settings.geocodificacao_url.rstrip("/")
        self.pais = settings.geocodificacao_pais
        self.user_agent = settings.geocodificacao_user_agent
        self.intervalo_s = settings.geocodificacao_intervalo_s
        self.transporte = transporte
        self._trava = asyncio.Lock()
        self._ultima = 0.0
        self._cache: OrderedDict[tuple[str, int], tuple[float, list[dict]]] = OrderedDict()
        self._cache_ttl_s = 24 * 3600
        self._cache_max = 500

    async def buscar(self, consulta: str, limite: int = 5) -> list[dict]:
        chave = (" ".join(consulta.lower().split()), limite)
        guardado = self._cache.get(chave)
        if guardado and time.monotonic() - guardado[0] < self._cache_ttl_s:
            self._cache.move_to_end(chave)
            return guardado[1]
        async with self._trava:  # respeita o limite de requisições do provedor
            espera = self.intervalo_s - (time.monotonic() - self._ultima)
            if espera > 0:
                await asyncio.sleep(espera)
            try:
                async with httpx.AsyncClient(timeout=10, transport=self.transporte) as client:
                    resposta = await client.get(
                        f"{self.url}/search",
                        params={"q": consulta, "format": "jsonv2", "limit": limite, "countrycodes": self.pais,
                                "accept-language": "pt-BR"},
                        headers={"User-Agent": self.user_agent},
                    )
            except httpx.HTTPError as erro:
                raise GeocodificacaoErro(f"geocodificação indisponível: {erro.__class__.__name__}") from erro
            finally:
                self._ultima = time.monotonic()
        if resposta.status_code != 200:
            raise GeocodificacaoErro(f"geocodificação recusou a consulta (HTTP {resposta.status_code})")
        try:
            resultados = [self._resultado(item) for item in resposta.json()]
        except (ValueError, TypeError, KeyError) as erro:
            raise GeocodificacaoErro("geocodificação respondeu fora do formato esperado") from erro
        self._cache[chave] = (time.monotonic(), resultados)
        if len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return resultados

    @staticmethod
    def _resultado(item: dict) -> dict:
        lat, lng = float(item["lat"]), float(item["lon"])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("coordenada fora da faixa")
        # N/W/R + osm_id identifica o lugar no OpenStreetMap; place_id muda entre instâncias.
        tipo_osm = str(item.get("osm_type") or "")[:1].upper()
        identificador = f"{tipo_osm}{item['osm_id']}" if tipo_osm and item.get("osm_id") else str(item["place_id"])
        return {"id": identificador, "endereco": str(item["display_name"]), "lat": lat, "lng": lng,
                "tipo": item.get("type")}
