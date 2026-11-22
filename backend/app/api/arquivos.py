"""Arquivos reais anexados ao CCO; o backend atual não possui autorização por usuário."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..servicos import arquivos
from .deps import c, erro_http
from .schemas import ArquivoRotaOut, CategoriaArquivo

router = APIRouter(tags=["arquivos"])


@router.get("/rotas/{rota_id}/arquivos", response_model=list[ArquivoRotaOut])
def listar(rota_id: int):
    try:
        return arquivos.listar(rota_id)
    except HTTPException:
        raise
    except Exception as error:
        raise erro_http(error)


@router.post("/rotas/{rota_id}/arquivos", status_code=201, response_model=ArquivoRotaOut)
async def adicionar(rota_id: int, arquivo: UploadFile = File(...),
                    categoria: CategoriaArquivo = Form("documento"),
                    descricao: Optional[str] = Form(None, max_length=1000), ct=Depends(c)):
    try:
        return await arquivos.adicionar(ct, rota_id, arquivo, categoria, descricao)
    except HTTPException:
        raise
    except Exception as error:
        raise erro_http(error)


@router.get("/rotas/{rota_id}/arquivos/{arquivo_id}/download")
def download(rota_id: int, arquivo_id: int, ct=Depends(c)):
    try:
        item, path = arquivos.obter(ct, rota_id, arquivo_id)
    except HTTPException:
        raise
    except Exception as error:
        raise erro_http(error)
    return FileResponse(path, media_type=item.tipo_mime, filename=item.nome_original,
                        content_disposition_type="attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
