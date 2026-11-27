"""Lê o backend (EventoGeo, Ocorrencia, Estadia, Evento) e monta a lista de `OcorrenciaEdi` da rota.

É a única parte do conector que toca o banco; `ocoren.gerar` continua puro e recebe o resultado pronto.
"""
from sqlmodel import select

from ...dominio.enums import TipoEvento, TipoGeo
from ...infra.db import sessao
from ...infra.models import Estadia, Evento, EventoGeo, Ocorrencia, Rota
from . import codigos
from .ocoren import OcorrenciaEdi

# Eventos simples: 1 linha na `tabela Evento`, sem campos extras a carregar (o timestamp já é a prova).
_EVENTOS_SIMPLES = {
    TipoEvento.NAO_RECEBE_HOJE: "nao_recebe_hoje",
    TipoEvento.LIGACAO_NAO_ATENDIDA: "ligacao_nao_atendida",
}


def ocorrencias_da_rota(rota_id: int) -> list[OcorrenciaEdi]:
    """Ordem cronológica. `descarga` (a linha 001/01 principal) só aparece com a estadia encerrada."""
    with sessao() as s:
        rota = s.get(Rota, rota_id)
        if not rota:
            return []
        itens: list[OcorrenciaEdi] = []

        retirada = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id,
                                                   EventoGeo.tipo == TipoGeo.RETIRADA)).first()
        if retirada:
            itens.append(OcorrenciaEdi(evento="retirada", quando=retirada.timestamp))

        aproximacao = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id,
                                                      EventoGeo.tipo == TipoGeo.APROXIMACAO)).first()
        if aproximacao:
            itens.append(OcorrenciaEdi(evento="aproximacao", quando=aproximacao.timestamp))

        chegada = s.exec(select(EventoGeo).where(EventoGeo.rota_id == rota_id,
                                                  EventoGeo.tipo == TipoGeo.CHEGADA)).first()
        estadia = s.exec(select(Estadia).where(Estadia.rota_id == rota_id).order_by(Estadia.id.desc())).first()
        if estadia and estadia.fim is not None:
            chegada_em = chegada.timestamp if chegada else estadia.inicio
            horas = max(0.0, (estadia.fim - chegada_em).total_seconds()) / 3600
            itens.append(OcorrenciaEdi(
                evento="descarga", quando=estadia.fim, chegada_em=chegada_em,
                descarga_inicio_em=estadia.descarga_inicio_em, descarga_fim_em=estadia.fim,
                saida_destino_em=estadia.saida_destino_em,
                texto_livre=f"ESPERA {int(horas):02d}H{round((horas % 1) * 60):02d}",
            ))

        for ocorrencia in s.exec(select(Ocorrencia).where(Ocorrencia.rota_id == rota_id)
                                 .order_by(Ocorrencia.id)).all():
            chave = codigos.OCORRENCIA_TIPO_PARA_CHAVE.get(ocorrencia.tipo)
            if chave:
                itens.append(OcorrenciaEdi(evento=chave, quando=ocorrencia.timestamp, observacao=ocorrencia.descricao))

        if rota.cancelada_em:
            itens.append(OcorrenciaEdi(evento="rota_cancelada", quando=rota.cancelada_em))

        for evento in s.exec(select(Evento).where(Evento.rota_id == rota_id,
                                                   Evento.tipo.in_([str(t) for t in _EVENTOS_SIMPLES]))
                             .order_by(Evento.id)).all():
            itens.append(OcorrenciaEdi(evento=_EVENTOS_SIMPLES[TipoEvento(evento.tipo)], quando=evento.timestamp))

    itens.sort(key=lambda item: item.quando)
    return itens
