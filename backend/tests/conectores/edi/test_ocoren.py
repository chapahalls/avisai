"""Geração do OCOREN: fixtures byte-exatas no cabeçalho e round-trip gerar -> ler nos campos de negócio.

`ocoren.gerar` é puro (sem banco/relógio); o cenário é o da demo: 11h40 de espera, rota com NF-e, CNPJ e
embarcador cadastrados.
"""
from datetime import datetime, UTC
from types import SimpleNamespace

import pytest

from app.conectores.edi import nfe, ocoren
from app.conectores.edi.layouts import ocoren_31, ocoren_50
from app.conectores.edi.motor import ler
from app.conectores.edi.ocoren import LayoutDesconhecido, OcorrenciaEdi

CHAVE = nfe.gerar_chave(cuf="35", aamm="2611", cnpj="12345678000195", serie="1", numero="23456789",
                        codigo_numerico="00000001")  # 8 dígitos significativos: cabe tanto no 542 (9) quanto no 342 (8)
CHEGADA = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)  # 05:00 em America/Sao_Paulo (UTC-3)
FIM = datetime(2026, 11, 27, 19, 40, tzinfo=UTC)  # 16:40 local; 11h40 de espera desde a chegada
AGORA = datetime(2026, 11, 27, 19, 41, tzinfo=UTC)


def _parceiro(layout="ocoren-5.0", **extra):
    base = dict(layout=layout, caixa_remetente="", caixa_destinatario="", depara={}, campos_extras={},
                codificacao="cp1252", fim_de_linha="\r\n")
    base.update(extra)
    return SimpleNamespace(**base)


def _transportadora(**extra):
    base = dict(id=1, cnpj="98765432000110", razao_social="Rota Sul Transportes Ltda", nome="Rota Sul")
    base.update(extra)
    return SimpleNamespace(**base)


def _rota(**extra):
    base = dict(nfe_chave=CHAVE, embarcador_nome="Atacado Sorocaba", recebedor_empresa="Atacado Sorocaba",
                romaneio="RM123")
    base.update(extra)
    return SimpleNamespace(**base)


def _descarga(**extra):
    base = dict(evento="descarga", quando=FIM, chegada_em=CHEGADA, descarga_fim_em=FIM,
                texto_livre="espera 11h40")
    base.update(extra)
    return OcorrenciaEdi(**base)


def test_todas_as_linhas_tem_o_tamanho_fixo_do_layout():
    conteudo = ocoren.gerar(_parceiro(), _transportadora(), _rota(), [_descarga()], AGORA, 7)
    linhas = conteudo.decode("cp1252").split("\r\n")[:-1]  # o último "\r\n" deixa uma linha vazia no final
    assert [len(l) for l in linhas] == [250, 250, 250, 250]
    assert [l[:3] for l in linhas] == ["000", "540", "541", "542"]


def test_cabecalho_000_e_byte_exato():
    conteudo = ocoren.gerar(_parceiro(), _transportadora(), _rota(), [], AGORA, 7)
    linha_000 = conteudo.decode("cp1252").split("\r\n")[0]
    assert linha_000[0:3] == "000"
    assert linha_000[3:38] == "Rota Sul Transportes Ltda".ljust(35)
    assert linha_000[38:73] == "Atacado Sorocaba".ljust(35)
    assert linha_000[73:79] == "271126"  # DDMMAA local (agora = 2026-11-27 19:41 UTC = 16:41 local)
    assert linha_000[79:83] == "1641"
    assert linha_000[83:95] == "OCO502711007".ljust(12)
    assert linha_000[95:250] == " " * 155


def test_541_traz_o_cnpj_e_a_razao_social_da_transportadora():
    conteudo = ocoren.gerar(_parceiro(), _transportadora(), _rota(), [], AGORA, 7)
    linha_541 = conteudo.decode("cp1252").split("\r\n")[2]
    valores = ler(linha_541, ocoren_50.REGISTRO_541)
    assert str(valores["cnpj_transportadora"]) == "98765432000110"
    assert valores["razao_social"] == "Rota Sul Transportes Ltda"


def test_542_preenche_os_campos_19_a_24_com_a_espera_de_11h40():
    conteudo = ocoren.gerar(_parceiro(), _transportadora(), _rota(), [_descarga()], AGORA, 7)
    linha_542 = conteudo.decode("cp1252").split("\r\n")[3]
    valores = ler(linha_542, ocoren_50.REGISTRO_542)
    assert valores["codigo_ocorrencia"] == 1  # De-Para padrão: "descarga" -> 001
    assert valores["chegada_destino_data"] == 27112026
    assert valores["chegada_destino_hora"] == 500
    assert valores["termino_descarga_data"] == 27112026
    assert valores["termino_descarga_hora"] == 1640
    # Campos 21-22/25-26 (início da descarga e saída do destino): ninguém os popula hoje, ficam vazios
    # sem quebrar o arquivo — é o caso condicional que o próprio manual prevê.
    assert valores["inicio_descarga_data"] is None
    assert valores["saida_destino_data"] is None
    assert valores["romaneio"] == "RM123"
    assert valores["numero_nf"] == 23456789


def test_ocorrencia_sem_codigo_no_depara_e_ignorada():
    desconhecida = OcorrenciaEdi(evento="evento_nao_mapeado", quando=FIM)
    conteudo = ocoren.gerar(_parceiro(), _transportadora(), _rota(), [desconhecida], AGORA, 7)
    linhas = conteudo.decode("cp1252").split("\r\n")[:-1]
    assert [l[:3] for l in linhas] == ["000", "540", "541"]  # nenhum 542 foi gerado


def test_depara_do_parceiro_sobrepoe_o_padrao_do_layout():
    parceiro = _parceiro(depara={"descarga": "005"})
    conteudo = ocoren.gerar(parceiro, _transportadora(), _rota(), [_descarga()], AGORA, 7)
    linha_542 = conteudo.decode("cp1252").split("\r\n")[3]
    assert ler(linha_542, ocoren_50.REGISTRO_542)["codigo_ocorrencia"] == 5


def test_layout_3_1_usa_texto_livre_em_vez_dos_campos_19_26_e_fica_em_maiuscula():
    conteudo = ocoren.gerar(_parceiro(layout="ocoren-3.1", fim_de_linha="\r\n"), _transportadora(), _rota(),
                            [_descarga()], AGORA, 7)
    linhas = conteudo.decode("cp1252").split("\r\n")[:-1]
    assert [len(l) for l in linhas] == [120, 120, 120, 120]
    linha_342 = linhas[3]
    valores = ler(linha_342, ocoren_31.REGISTRO_342)
    assert valores["codigo_ocorrencia"] == 1  # De-Para da 3.1: "descarga" -> 01 (2 dígitos)
    assert valores["texto_livre"] == "ESPERA 11H40"  # maiuscula=True no layout da 3.1


def test_layout_desconhecido_e_erro():
    with pytest.raises(LayoutDesconhecido):
        ocoren.gerar(_parceiro(layout="ocoren-9.9"), _transportadora(), _rota(), [], AGORA, 7)


def test_sem_chave_de_nfe_e_erro():
    with pytest.raises(ValueError, match="44 dígitos"):
        ocoren.gerar(_parceiro(), _transportadora(), _rota(nfe_chave=""), [], AGORA, 7)


def test_sem_cnpj_da_transportadora_e_erro():
    with pytest.raises(ValueError, match="CNPJ"):
        ocoren.gerar(_parceiro(), _transportadora(cnpj=""), _rota(), [], AGORA, 7)
