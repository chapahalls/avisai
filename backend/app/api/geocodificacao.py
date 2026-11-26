"""Busca de endereço para o cadastro de rota: o CCO escolhe um resultado e a coordenada fica vinculada."""
from fastapi import APIRouter, Depends, HTTPException, Query

from .deps import c, erro_http, exigir_cco
from .schemas import GeocodificacaoOut

router = APIRouter(tags=["geocodificacao"])


@router.get("/geocodificacao", response_model=GeocodificacaoOut, dependencies=[Depends(exigir_cco)])
async def buscar(q: str = Query(min_length=3, max_length=300), limite: int = Query(5, ge=1, le=10), ct=Depends(c)):
    """Candidatos do provedor configurado. 503 sem provedor; 502 quando o provedor falha. Não grava nada."""
    geo = ct.geocodificador
    if geo is None:
        raise HTTPException(503, {"erro": "geocodificacao_nao_configurada"})
    consulta = " ".join(q.split())
    if len(consulta) < 3:
        raise HTTPException(422, "consulta curta demais")
    try:
        resultados = await geo.buscar(consulta, limite)
    except Exception as e:  # noqa: BLE001
        raise erro_http(e)
    return {"provedor": geo.provedor, "atribuicao": geo.atribuicao, "resultados": resultados}
