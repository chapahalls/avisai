"""Gera o arquivo OCOREN (5.0 ou 3.1) a partir do perfil do parceiro e das ocorrências da rota.

Puro: não acessa banco nem relógio. `fonte.py` monta as `OcorrenciaEdi`; `servicos/edi.py` decide a hora
e o número de sequência e grava/serve o arquivo.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Optional

from . import codigos, nfe
from .layouts import ocoren_31, ocoren_50
from .motor import Registro, formatar

FUSO_HORAS = -3  # America/Sao_Paulo, sem horário de verão (mesma convenção de settings.fuso_utc_horas)
_LAYOUTS = {ocoren_50.NOME: ocoren_50, ocoren_31.NOME: ocoren_31}


@dataclass(frozen=True)
class OcorrenciaEdi:
    """Um evento do RODAR a traduzir para uma linha 542/342. `evento` é a chave do De-Para (codigos.py)."""
    evento: str
    quando: datetime
    observacao: Optional[str] = None
    texto_livre: Optional[str] = None  # só a 3.1 usa (espera em texto livre; a 5.0 usa os campos 19-26)
    chegada_em: Optional[datetime] = None
    descarga_inicio_em: Optional[datetime] = None
    descarga_fim_em: Optional[datetime] = None
    saida_destino_em: Optional[datetime] = None


class LayoutDesconhecido(ValueError):
    pass


def _local(quando: datetime) -> datetime:
    if quando.tzinfo is not None:
        quando = quando.astimezone(UTC).replace(tzinfo=None)
    return quando + timedelta(hours=FUSO_HORAS)


def _cabecalho_data_hora(quando: datetime) -> tuple[str, str]:
    local = _local(quando)
    return local.strftime("%d%m%y"), local.strftime("%H%M")  # DDMMAA, HHMM (registro 000, nos dois layouts)


def _data_hora_8_4(quando: Optional[datetime]) -> tuple[Optional[str], Optional[str]]:
    if quando is None:
        return None, None
    local = _local(quando)
    return local.strftime("%d%m%Y"), local.strftime("%H%M")  # DDMMAAAA, HHMM (542 da 5.0)


def _data_hora_12(quando: Optional[datetime]) -> Optional[str]:
    if quando is None:
        return None
    return _local(quando).strftime("%d%m%Y%H%M")  # DDMMAAAAHHMM (342 da 3.1)


def _linha(registro: Registro, valores: dict) -> str:
    return formatar(registro, {"identificador": registro.id, **valores})


def _somente_digitos(texto: str) -> str:
    return "".join(caractere for caractere in (texto or "") if caractere.isdigit())


def gerar(parceiro, transportadora, rota, ocorrencias: list[OcorrenciaEdi], agora: datetime, seq: int) -> bytes:
    """`parceiro` é um `infra.models.ParceiroEdi`; `transportadora`, uma `Empresa`; `rota`, uma `Rota`."""
    camada = _LAYOUTS.get(getattr(parceiro, "layout", None))
    if camada is None:
        raise LayoutDesconhecido(f"layout desconhecido: {parceiro.layout!r}")
    registros = camada.REGISTROS

    cnpj_transportadora = _somente_digitos(transportadora.cnpj)
    if not cnpj_transportadora:
        raise ValueError("transportadora sem CNPJ: não é possível gerar o OCOREN")
    chave = nfe.ChaveNFe.parse(rota.nfe_chave)

    remetente = parceiro.caixa_remetente or transportadora.razao_social or transportadora.nome
    destinatario = parceiro.caixa_destinatario or rota.embarcador_nome or rota.recebedor_empresa

    data_cab, hora_cab = _cabecalho_data_hora(agora)
    dia_mes = _local(agora).strftime("%d%m")
    seq3 = f"{seq % 1000:03d}"
    prefixo_doc = "OCORR50" if camada is ocoren_50 else "OCORR31"
    prefixo_interc = "OCO50" if camada is ocoren_50 else "OCO31"

    linhas = [_linha(registros["000"], {
        "remetente": remetente, "destinatario": destinatario, "data": data_cab, "hora": hora_cab,
        "intercambio": f"{prefixo_interc}{dia_mes}{seq3}",
    })]
    documento = f"{prefixo_doc}{dia_mes}{seq3}"
    razao_social = transportadora.razao_social or transportadora.nome
    depara = parceiro.depara or {}

    if camada is ocoren_50:
        linhas.append(_linha(registros["540"], {"documento": documento}))
        linhas.append(_linha(registros["541"], {
            "cnpj_transportadora": cnpj_transportadora, "razao_social": razao_social,
        }))
        for ocorrencia in ocorrencias:
            codigo = codigos.codigo(parceiro.layout, ocorrencia.evento, depara)
            if codigo is None:
                continue
            data_evento, hora_evento = _data_hora_8_4(ocorrencia.quando)
            chegada_data, chegada_hora = _data_hora_8_4(ocorrencia.chegada_em)
            inicio_data, inicio_hora = _data_hora_8_4(ocorrencia.descarga_inicio_em)
            fim_data, fim_hora = _data_hora_8_4(ocorrencia.descarga_fim_em)
            saida_data, saida_hora = _data_hora_8_4(ocorrencia.saida_destino_em)
            linhas.append(_linha(registros["542"], {
                "cnpj_emissor_nf": chave.cnpj, "serie_nf": chave.serie, "numero_nf": chave.numero,
                "codigo_ocorrencia": codigo, "data_ocorrencia": data_evento, "hora_ocorrencia": hora_evento,
                "romaneio": rota.romaneio or None,
                "chegada_destino_data": chegada_data, "chegada_destino_hora": chegada_hora,
                "inicio_descarga_data": inicio_data, "inicio_descarga_hora": inicio_hora,
                "termino_descarga_data": fim_data, "termino_descarga_hora": fim_hora,
                "saida_destino_data": saida_data, "saida_destino_hora": saida_hora,
            }))
    else:
        linhas.append(_linha(registros["340"], {"documento": documento}))
        linhas.append(_linha(registros["341"], {
            "cnpj_transportadora": cnpj_transportadora, "razao_social": razao_social,
        }))
        for ocorrencia in ocorrencias:
            codigo = codigos.codigo(parceiro.layout, ocorrencia.evento, depara)
            if codigo is None:
                continue
            linhas.append(_linha(registros["342"], {
                "cnpj_emissor_nf": chave.cnpj, "serie_nf": chave.serie, "numero_nf": chave.numero,
                "codigo_ocorrencia": codigo, "data_hora_ocorrencia": _data_hora_12(ocorrencia.quando),
                "texto_livre": ocorrencia.texto_livre,
            }))

    fim_de_linha = parceiro.fim_de_linha or "\r\n"
    texto = fim_de_linha.join(linhas) + fim_de_linha
    return texto.encode(parceiro.codificacao or "cp1252", errors="strict")
