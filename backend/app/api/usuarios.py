"""Catálogo público de perfis da demonstração (leitura) e cadastro de operador da central."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends

from ..servicos import usuarios
from .deps import erro_http, exigir_cco
from .schemas import NovoOperador, PerfilUsuarioOut

router = APIRouter(tags=["usuarios"])


@router.get("/usuarios", response_model=list[PerfilUsuarioOut])
@router.get("/api/users", response_model=list[PerfilUsuarioOut])
def listar(role: Optional[Literal["cco", "driver"]] = None):
    return usuarios.listar(role)


@router.post("/usuarios", response_model=PerfilUsuarioOut, dependencies=[Depends(exigir_cco)])
def criar_operador(body: NovoOperador):
    """Cria um perfil `cco`. 409 = e-mail já usado por outro perfil ou motorista; 400 = nome ou e-mail inválido."""
    try:
        return usuarios.criar_cco(body.nome, body.email)
    except Exception as error:
        raise erro_http(error)
