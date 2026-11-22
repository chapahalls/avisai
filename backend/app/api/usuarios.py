"""Catálogo público de perfis da demonstração; não concede autorização."""
from typing import Literal, Optional

from fastapi import APIRouter

from ..servicos import usuarios
from .schemas import PerfilUsuarioOut

router = APIRouter(tags=["usuarios"])


@router.get("/usuarios", response_model=list[PerfilUsuarioOut])
@router.get("/api/users", response_model=list[PerfilUsuarioOut])
def listar(role: Optional[Literal["cco", "driver"]] = None):
    return usuarios.listar(role)
