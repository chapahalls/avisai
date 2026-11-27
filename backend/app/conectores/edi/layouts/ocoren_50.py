"""OCOREN 5.0 (250 posições), conforme o manual da Intelipost — layout padrão do RODAR (ver seção 2 do
docs/edi/ocoren-integracao.md: o 542 tem campos próprios para a prova da estadia, 19-26, que a 3.1 não tem).

Só dados: nenhuma função aqui lê ou grava nada. `ocoren.py` monta os valores; `motor.py` formata.
"""
from ..motor import Campo, Registro

NOME = "ocoren-5.0"
TAMANHO_REGISTRO = 250
MAIUSCULA = False  # a Intelipost não exige caixa alta na 5.0 (diferente da 3.1)
# Ordem de montagem do arquivo: 1 "000" > até 200 "540" > 1 "541" por "540" > até 9999 "542" por "541".
ORDEM = ("000", "540", "541", "542")

REGISTRO_000 = Registro(
    id="000", tamanho=TAMANHO_REGISTRO, minimo=1, maximo=1,
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="remetente", pos=4, tamanho=35, tipo="A", status="M"),
        Campo(nome="destinatario", pos=39, tamanho=35, tipo="A", status="M"),
        Campo(nome="data", pos=74, tamanho=6, tipo="N", status="M"),  # DDMMAA
        Campo(nome="hora", pos=80, tamanho=4, tipo="N", status="M"),  # HHMM
        Campo(nome="intercambio", pos=84, tamanho=12, tipo="A", status="M"),
        Campo(nome="filler", pos=96, tamanho=155, tipo="A", status="C"),
    ),
)

REGISTRO_540 = Registro(
    id="540", tamanho=TAMANHO_REGISTRO, minimo=0, maximo=200, por="000",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="documento", pos=4, tamanho=14, tipo="A", status="M"),
        Campo(nome="filler", pos=18, tamanho=233, tipo="A", status="C"),
    ),
)

REGISTRO_541 = Registro(
    id="541", tamanho=TAMANHO_REGISTRO, minimo=1, maximo=1, por="540",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="cnpj_transportadora", pos=4, tamanho=14, tipo="N", status="M"),
        Campo(nome="razao_social", pos=18, tamanho=50, tipo="A", status="C"),
        Campo(nome="filler", pos=68, tamanho=183, tipo="A", status="C"),
    ),
)

REGISTRO_542 = Registro(
    id="542", tamanho=TAMANHO_REGISTRO, minimo=0, maximo=9999, por="541",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="cnpj_emissor_nf", pos=4, tamanho=14, tipo="N", status="M"),
        Campo(nome="serie_nf", pos=18, tamanho=3, tipo="A", status="C"),
        Campo(nome="numero_nf", pos=21, tamanho=9, tipo="N", status="M"),
        Campo(nome="codigo_ocorrencia", pos=30, tamanho=3, tipo="N", status="M"),
        Campo(nome="data_ocorrencia", pos=33, tamanho=8, tipo="N", status="M"),  # DDMMAAAA
        Campo(nome="hora_ocorrencia", pos=41, tamanho=4, tipo="N", status="C"),  # HHMM
        Campo(nome="codigo_observacao", pos=45, tamanho=2, tipo="N", status="C"),
        Campo(nome="romaneio", pos=47, tamanho=20, tipo="A", status="C"),
        Campo(nome="identificacao_embarque_1", pos=67, tamanho=20, tipo="A", status="C"),
        Campo(nome="identificacao_embarque_2", pos=87, tamanho=20, tipo="A", status="C"),
        Campo(nome="identificacao_embarque_3", pos=107, tamanho=20, tipo="A", status="C"),
        Campo(nome="filial_conhecimento", pos=127, tamanho=10, tipo="A", status="C"),
        Campo(nome="serie_conhecimento", pos=137, tamanho=5, tipo="A", status="C"),
        Campo(nome="numero_conhecimento", pos=142, tamanho=12, tipo="A", status="C"),
        Campo(nome="tipo_entrega", pos=154, tamanho=1, tipo="A", status="C"),
        Campo(nome="codigo_empresa", pos=155, tamanho=5, tipo="A", status="C"),
        Campo(nome="filial_emissora_nf", pos=160, tamanho=5, tipo="A", status="C"),
        Campo(nome="chegada_destino_data", pos=165, tamanho=8, tipo="N", status="C"),
        Campo(nome="chegada_destino_hora", pos=173, tamanho=4, tipo="N", status="C"),
        Campo(nome="inicio_descarga_data", pos=177, tamanho=8, tipo="N", status="C"),
        Campo(nome="inicio_descarga_hora", pos=185, tamanho=4, tipo="N", status="C"),
        Campo(nome="termino_descarga_data", pos=189, tamanho=8, tipo="N", status="C"),
        Campo(nome="termino_descarga_hora", pos=197, tamanho=4, tipo="N", status="C"),
        Campo(nome="saida_destino_data", pos=201, tamanho=8, tipo="N", status="C"),
        Campo(nome="saida_destino_hora", pos=209, tamanho=4, tipo="N", status="C"),
        Campo(nome="cnpj_devolucao", pos=213, tamanho=14, tipo="N", status="C"),
        Campo(nome="serie_devolucao", pos=227, tamanho=3, tipo="A", status="C"),
        Campo(nome="numero_devolucao", pos=230, tamanho=9, tipo="N", status="C"),
        Campo(nome="filler", pos=239, tamanho=12, tipo="A", status="C"),
    ),
)

REGISTROS: dict[str, Registro] = {"000": REGISTRO_000, "540": REGISTRO_540, "541": REGISTRO_541, "542": REGISTRO_542}
