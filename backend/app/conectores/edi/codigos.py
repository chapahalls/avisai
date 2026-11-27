"""Códigos de ocorrência e o De-Para padrão (evento do RODAR -> código), editável por `ParceiroEdi.depara`.

A Intelipost documenta só os códigos usados no 540/541/542 (seção 1 do docs/edi/ocoren-integracao.md);
o manual fala em faixas 000-105 e 201-213 na 5.0 (sem o 038) e 00-99 na 3.1, mas não publica o restante.
Por isso as tabelas abaixo não tentam enumerar o intervalo inteiro: só os códigos que o RODAR de fato
emite hoje, mais os poucos citados pelo manual como referência geral.
"""

CODIGOS_50: dict[str, str] = {
    "000": "processo de transporte iniciado (retirada)",
    "001": "entrega realizada",
    "005": "falta de espaço no destino",
    "027": "roubo/furto de carga",
    "044": "fila de veículos na doca",
    "046": "responsável pelo recebimento ausente",
    "053": "mercadoria não embarcada",
    "058": "quebra mecânica",
    "076": "via interditada",
    "078": "avaria na carga",
    "079": "avaria na carga (parcial)",
    "091": "entrega programada (não recebe hoje)",
    "098": "chegada na cidade/filial de destino",
}

CODIGOS_31: dict[str, str] = {
    "00": "processo de transporte iniciado (retirada)",
    "01": "entrega realizada",
    "05": "falta de espaço no destino",
    "27": "roubo/furto de carga",
    "44": "fila de veículos na doca",
    "46": "responsável pelo recebimento ausente",
    "53": "mercadoria não embarcada",
    "58": "quebra mecânica",
    "76": "via interditada",
    "78": "avaria na carga",
    "91": "entrega programada (não recebe hoje)",
    "98": "chegada na cidade/filial de destino",
    "99": "aguardando descarga (fora do manual; combinar com o parceiro antes de usar)",
}

# Evento do RODAR (fonte.py) -> código do De-Para, por layout. `001`/`01` ("descarga") é a linha
# principal: o 542 da 5.0 carrega junto os campos 19-26, prova da estadia (seção 2 do documento).
DEPARA_PADRAO: dict[str, dict[str, str]] = {
    "ocoren-5.0": {
        "retirada": "000",
        "aproximacao": "098",
        "descarga": "001",
        "nao_recebe_hoje": "091",
        "ligacao_nao_atendida": "046",
        "fila_doca": "044",
        "ocorrencia_quebra": "058",
        "ocorrencia_roubo": "027",
        "ocorrencia_via_interditada": "076",
        "ocorrencia_avaria": "078",
        "rota_cancelada": "053",
    },
    "ocoren-3.1": {
        "retirada": "00",
        "aproximacao": "98",
        "descarga": "01",
        "nao_recebe_hoje": "91",
        "ligacao_nao_atendida": "46",
        "fila_doca": "44",
        "ocorrencia_quebra": "58",
        "ocorrencia_roubo": "27",
        "ocorrencia_via_interditada": "76",
        "ocorrencia_avaria": "78",
        "rota_cancelada": "53",
    },
}

# Ocorrência do RODAR (`Ocorrencia.tipo`, dominio/ocorrencias.py) -> chave do De-Para. Só os tipos em que
# a correspondência é inequívoca; os outros (acidente, atraso, documento, recusa, outro) ficam de fora
# até combinar o código certo com um parceiro real (mesma cautela do item "Em aberto" do documento).
OCORRENCIA_TIPO_PARA_CHAVE: dict[str, str] = {
    "avaria": "ocorrencia_avaria",
    "fila": "fila_doca",
    "doca_ocupada": "fila_doca",
}


def codigo(layout: str, evento: str, depara_parceiro: dict | None = None) -> str | None:
    """Resolve o código de um evento, com o De-Para do parceiro sobrepondo o padrão do layout."""
    tabela = {**DEPARA_PADRAO.get(layout, {}), **(depara_parceiro or {})}
    return tabela.get(evento)
