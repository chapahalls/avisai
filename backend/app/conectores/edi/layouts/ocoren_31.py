"""OCOREN 3.1 (120 posições), conforme o manual PROCEDA. Segunda especificação do motor (seção 2 do
docs/edi/ocoren-integracao.md): prova que uma variante nova custa uma tabela, não um adapter em código.

Diferenças da 5.0 que o layout carrega, não o código: registro mais curto, código de ocorrência com 2
dígitos, número da NF com 8 dígitos, campos A em maiúsculas, e a espera só cabe em texto livre (sem os
campos 19-26 da 5.0 para a prova da estadia).
"""
from ..motor import Campo, Registro

NOME = "ocoren-3.1"
TAMANHO_REGISTRO = 120
MAIUSCULA = True  # o manual PROCEDA exige maiúsculas nos campos A
ORDEM = ("000", "340", "341", "342")

REGISTRO_000 = Registro(
    id="000", tamanho=TAMANHO_REGISTRO, minimo=1, maximo=1,
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="remetente", pos=4, tamanho=35, tipo="A", status="M", maiuscula=True),
        Campo(nome="destinatario", pos=39, tamanho=35, tipo="A", status="M", maiuscula=True),
        Campo(nome="data", pos=74, tamanho=6, tipo="N", status="M"),  # DDMMAA
        Campo(nome="hora", pos=80, tamanho=4, tipo="N", status="M"),  # HHMM
        Campo(nome="intercambio", pos=84, tamanho=12, tipo="A", status="M", maiuscula=True),
        Campo(nome="filler", pos=96, tamanho=25, tipo="A", status="C"),
    ),
)

REGISTRO_340 = Registro(
    id="340", tamanho=TAMANHO_REGISTRO, minimo=0, maximo=200, por="000",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="documento", pos=4, tamanho=14, tipo="A", status="M", maiuscula=True),
        Campo(nome="filler", pos=18, tamanho=103, tipo="A", status="C"),
    ),
)

REGISTRO_341 = Registro(
    id="341", tamanho=TAMANHO_REGISTRO, minimo=1, maximo=1, por="340",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="cnpj_transportadora", pos=4, tamanho=14, tipo="N", status="M"),
        Campo(nome="razao_social", pos=18, tamanho=40, tipo="A", status="C", maiuscula=True),
        Campo(nome="filler", pos=58, tamanho=63, tipo="A", status="C"),
    ),
)

REGISTRO_342 = Registro(
    id="342", tamanho=TAMANHO_REGISTRO, minimo=0, maximo=9999, por="341",
    campos=(
        Campo(nome="identificador", pos=1, tamanho=3, tipo="N", status="M"),
        Campo(nome="cnpj_emissor_nf", pos=4, tamanho=14, tipo="N", status="M"),
        Campo(nome="serie_nf", pos=18, tamanho=3, tipo="A", status="C", maiuscula=True),
        Campo(nome="numero_nf", pos=21, tamanho=8, tipo="N", status="M"),
        Campo(nome="codigo_ocorrencia", pos=29, tamanho=2, tipo="N", status="M"),
        Campo(nome="data_hora_ocorrencia", pos=31, tamanho=12, tipo="N", status="M"),  # DDMMAAAAHHMM
        Campo(nome="codigo_observacao", pos=43, tamanho=2, tipo="N", status="C"),
        Campo(nome="texto_livre", pos=45, tamanho=70, tipo="A", status="C", maiuscula=True),
        Campo(nome="filler", pos=115, tamanho=6, tipo="A", status="C"),
    ),
)
# 343 (redespacho, condicional): não publicado/gerado — ver "Em aberto" no docs/edi/ocoren-integracao.md.

REGISTROS: dict[str, Registro] = {"000": REGISTRO_000, "340": REGISTRO_340, "341": REGISTRO_341, "342": REGISTRO_342}
