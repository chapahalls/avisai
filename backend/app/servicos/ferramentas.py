"""Ferramentas do LLM: registro {nome: Ferramenta}. Nova ferramenta = nova entrada (aberto/fechado)."""
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..dominio.enums import Papel
from ..infra.models import SessaoAgente
from . import central, ligacoes, reportes, tasks

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
    recebe = args.get("recebe_hoje")
    await ligacoes.registrar_resposta(c, sa.id, args.get("previsao"), args.get("doca"), args.get("motivo"),
                                      args.get("resumo") or fala, recebe_hoje=None if recebe is None else bool(recebe))
    return {"ok": True, "mensagem": "Resposta registrada e repassada ao motorista e ao CCO."}


async def _retirada(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    geo = await tasks.confirmar_retirada(c, sa.rota_id, transcricao=fala or args.get("observacao"))
    return {"ok": True, "validado": geo.status == "validado",
            "proximo": "peça o relatório inicial: como está o caminhão e a carga coletada"}


async def _relatorio_inicial(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    return reportes.registrar(c, sa.rota_id, "inicial", args, fala)


async def _checkin(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    return reportes.registrar(c, sa.rota_id, "checkin", args, fala)


async def _documento(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    from ..dominio import documentos
    from ..dominio.enums import TipoEvento
    from . import consultas

    r, _, empresa = consultas.contexto_rota(sa.rota_id)
    pergunta = args.get("pergunta") or fala
    res = documentos.consultar(documentos.da_rota(r, empresa), pergunta, args.get("documento"))
    c.eventos.registrar(TipoEvento.PERGUNTA_DOCUMENTO, f"Pergunta sobre documento: {pergunta} → {res['resposta']}",
                        sa.rota_id, pergunta=pergunta, encontrado=res["encontrado"], documento=res["documento"],
                        campo=res["campo"], _fonte="agent")
    return res


async def _responder_central(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    sol = central.responder(c, sa.rota_id, args.get("resposta") or fala, transcricao=fala)
    return {"ok": bool(sol), "mensagem": "Resposta enviada à central." if sol else "Não há pergunta da central pendente."}


REGISTRO: dict[str, Ferramenta] = {
    "confirmar_retirada": Ferramenta(
        Papel.MOTORISTA, "Motorista confirmou por voz a retirada da carga na origem.",
        {"type": "object", "properties": {"observacao": {"type": "string"}}},
        _retirada),
    "registrar_relatorio_inicial": Ferramenta(
        Papel.MOTORISTA, "Relatório inicial da viagem. Passe só os campos que o motorista disse; o sistema devolve o que falta perguntar.",
        {"type": "object", "properties": {
            "estado_caminhao": {"type": "string", "description": "Como está o caminhão."},
            "carga": {"type": "string", "description": "Carga coletada."}}},
        _relatorio_inicial),
    "registrar_checkin": Ferramenta(
        Papel.MOTORISTA, "Check-in na chegada. Passe só os campos que o motorista disse; o sistema devolve o que falta perguntar.",
        {"type": "object", "properties": {
            "status_carga": {"type": "string", "description": "Estado final da carga."},
            "tempo_viagem": {"type": "string", "description": "Tempo de viagem."},
            "problemas": {"type": "string", "description": "Problemas ou ocorrências; 'nenhum' se não houve."}}},
        _checkin),
    "consultar_documento": Ferramenta(
        Papel.MOTORISTA, "Consulta a NF-e ou o CT-e da viagem (número, peso, valor, destinatário, itens, frete, placa, chave). "
        "Responda só com o que voltar, citando o documento; se não encontrado, diga que não encontrou.",
        {"type": "object", "properties": {
            "pergunta": {"type": "string", "description": "A pergunta do motorista."},
            "documento": {"type": "string", "enum": ["NF-e", "CT-e"], "description": "Se ele disse qual documento."}},
         "required": ["pergunta"]},
        _documento),
    "responder_central": Ferramenta(
        Papel.MOTORISTA, "Envia à central a resposta do motorista para a pergunta pendente da central.",
        {"type": "object", "properties": {"resposta": {"type": "string", "description": "Resposta fiel e curta."}},
         "required": ["resposta"]},
        _responder_central),
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
            "resumo": {"type": "string", "description": "Resumo fiel, em uma frase, do que o recebedor disse."},
            "recebe_hoje": {"type": "boolean", "description": "false se o recebedor disse que não recebe hoje."}},
         "required": ["resumo"]},
        _resposta_recebedor),
}


def para(papel: str) -> dict[str, Ferramenta]:
    return {n: f for n, f in REGISTRO.items() if f.papel == papel}


def schemas(papel: str) -> list[dict]:
    return [f.schema(n) for n, f in para(papel).items()]
