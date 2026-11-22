"""Perfis persistidos da demonstração; login por e-mail conhecido, sem autenticação real."""
from typing import Optional

from sqlmodel import Session, select

from ..infra.db import sessao
from ..infra.models import Motorista, Usuario
from .consultas import NaoEncontrado


class ConflitoUsuario(ValueError):
    pass


def normalizar_email(email: str) -> str:
    normalized = email.strip().lower()
    if len(normalized) > 320 or normalized.count("@") != 1 or any(char.isspace() for char in normalized):
        raise ValueError("E-mail inválido")
    local, domain = normalized.split("@")
    if not local or not domain:
        raise ValueError("E-mail inválido")
    return normalized


def garantir_motorista(s: Session, motorista: Motorista) -> Optional[Usuario]:
    if not motorista.email:
        return None
    email = normalizar_email(motorista.email)
    existing = s.exec(select(Usuario).where(Usuario.email == email)).first()
    if existing:
        if existing.papel != "driver" or existing.motorista_id != motorista.id:
            raise ConflitoUsuario("E-mail já vinculado a outro perfil")
        return existing
    user = Usuario(email=email, papel="driver", motorista_id=motorista.id)
    s.add(user)
    return user


def garantir_cco(s: Session, email: str, nome: str) -> Usuario:
    email = normalizar_email(email)
    existing = s.exec(select(Usuario).where(Usuario.email == email)).first()
    if existing:
        if existing.papel != "cco":
            raise ConflitoUsuario("E-mail de demonstração já vinculado a motorista")
        return existing
    user = Usuario(email=email, nome=nome, papel="cco")
    s.add(user)
    return user


def _perfil(s: Session, user: Usuario) -> dict:
    from .publicacao import rota_atual

    driver = s.get(Motorista, user.motorista_id) if user.motorista_id is not None else None
    if user.papel == "driver" and driver is None:
        raise RuntimeError("Perfil de motorista sem cadastro vinculado")
    route = rota_atual(driver.id) if driver else None
    return {
        "id": str(user.id), "email": user.email, "name": driver.nome if driver else user.nome,
        "role": user.papel, "driverId": driver.id if driver else None,
        "tripId": str(route.id) if route else None,
    }


def listar(role: Optional[str] = None) -> list[dict]:
    with sessao() as s:
        query = select(Usuario)
        if role is not None:
            query = query.where(Usuario.papel == role)
        profiles = [_perfil(s, user) for user in s.exec(query).all()]
    return sorted(profiles, key=lambda profile: (profile["role"], profile["name"].casefold(), int(profile["id"])))


def por_email(email: str) -> dict:
    normalized = normalizar_email(email)
    with sessao() as s:
        user = s.exec(select(Usuario).where(Usuario.email == normalized)).first()
        if not user:
            raise NaoEncontrado("Perfil de demonstração não cadastrado")
        return _perfil(s, user)
