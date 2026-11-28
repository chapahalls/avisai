"""Conector OCOREN (docs/edi/ocoren-integracao.md): perfis de parceiro e geração/validação do arquivo.

Até 30/11 só existe download manual (sem SFTP/fila): o CCO pede o arquivo pronto e salva onde quiser.
"""
from fastapi import APIRouter, Depends, Query, Response, UploadFile, File

from ..servicos import edi
from .deps import c, erro_http, exigir_cco
from .schemas import ParceiroEdiIn, ParceiroEdiOut, ParceiroEdiPatch, ValidacaoEdiOut

router = APIRouter(tags=["edi"])


@router.get("/rotas/{rota_id}/ocoren", dependencies=[Depends(exigir_cco)])
def baixar_ocoren(
    rota_id: int,
    parceiro: int = Query(..., description="id do ParceiroEdi"),
    dry_run: bool = Query(False, description="Gera o arquivo sem consumir o número de sequência "
                          "(Empresa.ultima_sequencia_ocoren) — usado pelo smoke de deploy, nunca pelo CCO de verdade."),
    ct=Depends(c),
):
    """Gera o arquivo OCOREN (5.0 ou 3.1, conforme o perfil) e devolve para download. 409 sem NF-e/CNPJ."""
    try:
        nome, conteudo = edi.gerar_ocoren(ct, rota_id, parceiro, dry_run=dry_run)
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)
    return Response(conteudo, media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"',
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/edi/parceiros", response_model=list[ParceiroEdiOut], dependencies=[Depends(exigir_cco)])
def listar_parceiros(empresa_id: int | None = None):
    try:
        return edi.listar_parceiros(empresa_id)
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)


@router.post("/edi/parceiros", status_code=201, response_model=ParceiroEdiOut, dependencies=[Depends(exigir_cco)])
def criar_parceiro(dados: ParceiroEdiIn):
    try:
        return edi.criar_parceiro(dados.model_dump())
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)


@router.patch("/edi/parceiros/{parceiro_id}", response_model=ParceiroEdiOut, dependencies=[Depends(exigir_cco)])
def atualizar_parceiro(parceiro_id: int, dados: ParceiroEdiPatch):
    try:
        return edi.atualizar_parceiro(parceiro_id, dados.model_dump(exclude_unset=True))
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)


@router.post("/edi/validar", response_model=ValidacaoEdiOut, dependencies=[Depends(exigir_cco)])
async def validar(layout: str = Query(...), codificacao: str = Query("cp1252"), arquivo: UploadFile = File(...)):
    """Valida um arquivo OCOREN já recebido (homologação com o parceiro): erro por linha/campo, sem gravar nada."""
    try:
        conteudo = await arquivo.read()
        return edi.validar_arquivo(conteudo, layout, codificacao)
    except Exception as error:  # noqa: BLE001
        raise erro_http(error)
