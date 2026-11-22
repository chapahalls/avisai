"""Ferramentas do LLM: registro {nome: Ferramenta}. Nova ferramenta = nova entrada (aberto/fechado)."""
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..dominio.enums import Papel
from ..infra.models import SessaoAgente
from . import ligacoes, tasks

Handler = Callable[..., Awaitable[dict]]


@dataclass(frozen=True)
class Ferramenta:
    papel: str
    descricao: str
    parametros: dict
    executar: Handler  # (c, sessao, args, fala) -> dict

    def schema(self, nome: str) -> dict:
        return {"type": "function", "function": {"name": nome, "description": self.descricao, "parameters": self.parametros}}


async def _chegada(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    t = await tasks.on_chegada(c, sa.rota_id, origem="voz", transcricao=fala or args.get("observacao"))
    return {"ok": True, "task_id": t.id, "mensagem": "Chegada registrada, CCO avisado, estadia contando."}


async def _ocorrencia(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    o = tasks.registrar_ocorrencia(c, sa.rota_id, args.get("tipo", "outro"), args.get("descricao") or fala, transcricao=fala)
    return {"ok": True, "ocorrencia_id": o.id}


async def _descarga(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    x = await tasks.confirmar_descarga(c, sa.rota_id, por="motorista (voz)", transcricao=fala or args.get("observacao"))
    return {"ok": True, "tempo_parado": x.get("tempo_parado"), "estadia": x.get("valor_fmt")}


async def _resposta_recebedor(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    await ligacoes.registrar_resposta(c, sa.id, args.get("previsao"), args.get("doca"), args.get("motivo"),
                                      args.get("resumo") or fala)
    return {"ok": True, "mensagem": "Resposta registrada e repassada ao motorista e ao CCO."}


REGISTRO: dict[str, Ferramenta] = {
    "confirmar_chegada": Ferramenta(
        Papel.MOTORISTA, "Motorista confirmou por voz que chegou ao destino (portaria, pátio, recebedor).",
        {"type": "object", "properties": {"observacao": {"type": "string", "description": "O que o motorista disse, resumido."}}},
        _chegada),
    "registrar_ocorrencia": Ferramenta(
        Papel.MOTORISTA, "Registra problema relatado pelo motorista: fila, doca ocupada, documento, avaria, atraso, recusa, acidente.",
        {"type": "object", "properties": {
            "tipo": {"type": "string", "enum": ["fila", "doca_ocupada", "documento", "avaria", "atraso", "recusa", "acidente", "outro"]},
            "descricao": {"type": "string", "description": "Descrição curta e fiel do relato."}},
         "required": ["tipo", "descricao"]},
        _ocorrencia),
    "confirmar_descarga": Ferramenta(
        Papel.MOTORISTA, "Motorista confirmou que a carga foi descarregada. Encerra a estadia e a Task.",
        {"type": "object", "properties": {"observacao": {"type": "string"}}},
        _descarga),
    "registrar_resposta_recebedor": Ferramenta(
        Papel.RECEBEDOR, "Registra a resposta do recebimento (previsão de descarga, doca, motivo da espera). Chame assim que tiver a resposta.",
        {"type": "object", "properties": {
            "previsao": {"type": "string", "description": "Ex.: 'em 40 minutos', 'às 15h', 'não recebe hoje'."},
            "doca": {"type": "string"},
            "motivo": {"type": "string", "description": "Motivo da espera ou pedido de documento."},
            "resumo": {"type": "string", "description": "Resumo fiel, em uma frase, do que o recebedor disse."}},
         "required": ["resumo"]},
        _resposta_recebedor),
}


def para(papel: str) -> dict[str, Ferramenta]:
    return {n: f for n, f in REGISTRO.items() if f.papel == papel}


def schemas(papel: str) -> list[dict]:
    return [f.schema(n) for n, f in para(papel).items()]
