"""Ferramentas do LLM: registro {nome: Ferramenta}. Nova ferramenta = nova entrada (aberto/fechado)."""
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..dominio.enums import Papel
from ..infra.models import SessaoAgente
from . import chamadas_agente, chamados, central, ligacoes, mensagens, reportes, tasks

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
    from ..dominio import ocorrencias as roteiro

    descricao = str(args.get("descricao") or fala).strip()
    km = args.get("km")
    try:
        km = float(km) if km is not None else None
    except (TypeError, ValueError):
        km = None
    if not descricao:
        return {"ok": False, "erro": "Descrição da ocorrência ausente."}
    o = tasks.registrar_ocorrencia(
        c, sa.rota_id, args.get("tipo", "outro"), descricao, transcricao=fala, km=km, rodovia=args.get("rodovia"),
    )
    chamado = await chamados.abrir_ocorrencia(c, sa.rota_id, o, transcricao=fala)
    return {
        "ok": True,
        "ocorrencia_id": o.id,
        "chamado_id": chamado.id,
        "faltando": o.faltantes,
        "pergunte_agora": roteiro.proxima(o.tipo, o.faltantes),
        "instrucao": "Não encerre no 'registrei': faça as perguntas, uma por vez, e registre cada resposta com detalhar_ocorrencia.",
    }


async def _detalhar(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    return tasks.detalhar_ocorrencia(c, sa.rota_id, args, transcricao=fala)


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


async def _responder_mensagem_motorista(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    mensagem = mensagens.responder(c, sa.rota_id, args.get("resposta") or fala, transcricao=fala)
    return {
        "ok": bool(mensagem),
        "mensagem": "Resposta enviada à CCO." if mensagem else "Não há mensagem pendente da CCO.",
        "mensagem_id": mensagem.id if mensagem else None,
    }


async def _ligar(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    chamada = await chamadas_agente.ligar(
        c,
        sa.rota_id,
        args.get("destino", "operador"),
        args.get("motivo") or fala,
        iniciado_por="llm",
    )
    return {
        "ok": chamada.status in ("twilio_atendida", "agora_tocando", "atendida"),
        "chamada_id": chamada.id,
        "status": chamada.status,
        "twilio_resultado": chamada.twilio_resultado,
    }


async def _comandar_app(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    from ..dominio import comandos_app

    cmd, erro = comandos_app.validar(args)
    if not cmd:
        return {"ok": False, "erro": erro}
    if cmd.acao == "sair_da_conta" and not cmd.confirmado:
        return {"ok": False, "pergunte_agora": comandos_app.PEDIR_CONFIRMACAO_SAIR,
                "instrucao": "Só chame de novo com confirmado=true depois que ele confirmar."}
    c.eventos.publicar("acao_cliente", comandos_app.payload_cliente(sa.rota_id, cmd), sa.rota_id)
    return {"ok": True, "diga": comandos_app.fala_confirmacao(cmd)}


async def _falar_motorista(c, sa: SessaoAgente, args: dict, fala: str) -> dict:
    mensagem = await mensagens.falar_motorista(
        c,
        sa.rota_id,
        args.get("remetente") or "Operador CCO",
        args.get("texto") or fala,
    )
    return {"ok": mensagem.status != "offline", "mensagem_id": mensagem.id, "status": mensagem.status}


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
    "responder_mensagem_motorista": Ferramenta(
        Papel.MOTORISTA, "Vincula a resposta por voz do motorista à última mensagem falada pela CCO.",
        {"type": "object", "properties": {"resposta": {"type": "string", "description": "Resposta fiel e curta."}},
         "required": ["resposta"]},
        _responder_mensagem_motorista),
    "ligar": Ferramenta(
        Papel.MOTORISTA, "Liga para um humano quando o motorista pedir ajuda; usa Twilio e fallback Agora RTC auditáveis.",
        {"type": "object", "properties": {
            "destino": {"type": "string", "enum": ["operador", "supervisor", "motorista"]},
            "motivo": {"type": "string", "description": "Motivo fiel e curto da ligação."}},
         "required": ["destino", "motivo"]},
        _ligar),
    "comandar_app": Ferramenta(
        Papel.MOTORISTA, "Comanda o app do motorista por voz: abrir uma tela, abrir um documento, voltar, "
        "encerrar a conversa ou sair da conta. Use quando ele PEDIR para ver ou abrir algo no app; "
        "para responder perguntas sobre a nota ou o CT-e, use consultar_documento.",
        {"type": "object", "properties": {
            "acao": {"type": "string", "enum": ["abrir_tela", "abrir_documento", "voltar", "encerrar_conversa", "sair_da_conta"]},
            "tela": {"type": "string", "enum": ["inicio", "mapa", "documentos", "mensagens", "fila"],
                     "description": "Para abrir_tela. fila = fila no recebedor (doca e tempo parado)."},
            "documento": {"type": "string", "description": "Para abrir_documento: NF-e, CT-e ou o nome do anexo que ele disse."},
            "confirmado": {"type": "boolean", "description": "Para sair_da_conta: true só depois que ele confirmar."}},
         "required": ["acao"]},
        _comandar_app),
    "confirmar_chegada": Ferramenta(
        Papel.MOTORISTA, "Motorista confirmou por voz que chegou ao destino (portaria, pátio, recebedor).",
        {"type": "object", "properties": {"observacao": {"type": "string", "description": "O que o motorista disse, resumido."}}},
        _chegada),
    "registrar_ocorrencia": Ferramenta(
        Papel.MOTORISTA, "Registra uma ocorrência e abre um chamado para o CCO. Use km e rodovia somente se o motorista informar.",
        {"type": "object", "properties": {
            "tipo": {"type": "string", "enum": ["fila", "doca_ocupada", "documento", "avaria", "atraso", "recusa", "acidente", "outro"]},
            "descricao": {"type": "string", "description": "Descrição curta e fiel do problema."},
            "km": {"type": "number", "description": "Quilômetro informado pelo motorista."},
            "rodovia": {"type": "string", "description": "Rodovia, por exemplo BR-381."}},
         "required": ["tipo", "descricao"]},
        _ocorrencia),
    "detalhar_ocorrencia": Ferramenta(
        Papel.MOTORISTA, "Registra as respostas do motorista às perguntas de aprofundamento da ocorrência aberta. "
        "Passe só os campos que ele respondeu; o sistema devolve a próxima pergunta (pergunte_agora).",
        {"type": "object", "properties": {
            "feridos": {"type": "string", "description": "acidente: 'sim' ou 'não'"},
            "envolvido": {"type": "string", "description": "acidente: se o caminhão se envolveu"},
            "consegue_seguir": {"type": "string", "description": "'sim' ou 'não'"},
            "local": {"type": "string", "description": "rodovia, km, referência"},
            "o_que": {"type": "string", "description": "avaria: o que aconteceu"},
            "carga": {"type": "string", "description": "avaria: se a carga foi afetada"},
            "quanto": {"type": "string", "description": "atraso: quanto tempo"},
            "motivo": {"type": "string"},
            "quantos": {"type": "string", "description": "fila: caminhões na frente"},
            "previsao": {"type": "string"},
            "outra_doca": {"type": "string"},
            "qual": {"type": "string", "description": "documento pedido"},
            "quem": {"type": "string"},
            "detalhe": {"type": "string"}}},
        _detalhar),
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
    "falar_motorista": Ferramenta(
        Papel.OPERADOR, "Envia uma mensagem do operador ao motorista e pede uma resposta por voz.",
        {"type": "object", "properties": {
            "remetente": {"type": "string", "description": "Nome do operador ou remetente."},
            "texto": {"type": "string", "description": "Mensagem curta para o motorista."}},
         "required": ["texto"]},
        _falar_motorista),
}


def para(papel: str) -> dict[str, Ferramenta]:
    return {n: f for n, f in REGISTRO.items() if f.papel == papel}


def schemas(papel: str) -> list[dict]:
    return [f.schema(n) for n, f in para(papel).items()]
