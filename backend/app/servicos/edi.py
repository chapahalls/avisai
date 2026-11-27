"""Serviço do conector OCOREN: perfis de parceiro (`ParceiroEdi`), geração do arquivo e validação de um
arquivo recebido. A geração em si (`conectores/edi/ocoren.py`) é pura; aqui entram banco e relógio."""
from typing import Optional

from sqlmodel import select

from ..conectores.edi import codigos, fonte, ocoren
from ..conectores.edi.layouts import ocoren_31, ocoren_50
from ..conectores.edi.motor import ErroEdi, ler
from ..infra.db import sessao
from ..infra.models import Empresa, ParceiroEdi, Rota
from . import consultas

LAYOUTS = {ocoren_50.NOME: ocoren_50, ocoren_31.NOME: ocoren_31}


def listar_parceiros(empresa_id: Optional[int] = None) -> list[ParceiroEdi]:
    with sessao() as s:
        consulta = select(ParceiroEdi)
        if empresa_id is not None:
            consulta = consulta.where(ParceiroEdi.empresa_id == empresa_id)
        return s.exec(consulta.order_by(ParceiroEdi.id)).all()


def criar_parceiro(dados: dict) -> ParceiroEdi:
    if dados.get("layout") not in LAYOUTS:
        raise ValueError(f"layout desconhecido: {dados.get('layout')!r}. Use um de {sorted(LAYOUTS)}")
    with sessao() as s:
        parceiro = ParceiroEdi(**dados)
        s.add(parceiro)
        s.commit()
        s.refresh(parceiro)
        return parceiro


def atualizar_parceiro(parceiro_id: int, dados: dict) -> ParceiroEdi:
    if "layout" in dados and dados["layout"] not in LAYOUTS:
        raise ValueError(f"layout desconhecido: {dados['layout']!r}. Use um de {sorted(LAYOUTS)}")
    with sessao() as s:
        parceiro = s.get(ParceiroEdi, parceiro_id)
        if not parceiro:
            raise consultas.NaoEncontrado(f"parceiro de EDI {parceiro_id} não existe")
        for campo, valor in dados.items():
            setattr(parceiro, campo, valor)
        s.add(parceiro)
        s.commit()
        s.refresh(parceiro)
        return parceiro


_SEQUENCIA: dict[int, int] = {}  # empresa_id -> último nº usado neste processo (só evita colisão de nome)


def _proxima_sequencia(empresa_id: int) -> int:
    _SEQUENCIA[empresa_id] = _SEQUENCIA.get(empresa_id, 0) + 1
    return _SEQUENCIA[empresa_id]


def _somente_digitos(texto: str) -> str:
    return "".join(caractere for caractere in (texto or "") if caractere.isdigit())


def gerar_ocoren(c, rota_id: int, parceiro_id: int) -> tuple[str, bytes]:
    """Devolve (nome_do_arquivo, conteúdo). `consultas.ConflitoEstado` (409) sem NF-e ou CNPJ cadastrados."""
    with sessao() as s:
        rota = s.get(Rota, rota_id)
        if not rota:
            raise consultas.NaoEncontrado(f"rota {rota_id} não existe")
        parceiro = s.get(ParceiroEdi, parceiro_id)
        if not parceiro:
            raise consultas.NaoEncontrado(f"parceiro de EDI {parceiro_id} não existe")
        transportadora = s.get(Empresa, rota.empresa_id)
    if not rota.nfe_chave:
        raise consultas.ConflitoEstado(f"rota {rota_id} não tem chave de NF-e cadastrada (Rota.nfe_chave)")
    if not transportadora or not _somente_digitos(transportadora.cnpj):
        raise consultas.ConflitoEstado(f"transportadora da rota {rota_id} não tem CNPJ cadastrado (Empresa.cnpj)")
    ocorrencias = fonte.ocorrencias_da_rota(rota_id)
    agora = c.relogio.agora()
    conteudo = ocoren.gerar(parceiro, transportadora, rota, ocorrencias, agora, _proxima_sequencia(transportadora.id))
    nome = f"OCOREN_{_somente_digitos(transportadora.cnpj)}_{agora:%d%m%H%M}.txt"
    return nome, conteudo


def validar_arquivo(conteudo: bytes, layout: str, codificacao: str = "cp1252") -> dict:
    """Lê um arquivo OCOREN linha a linha e devolve os erros por linha/campo (ajuda na homologação)."""
    camada = LAYOUTS.get(layout)
    if camada is None:
        raise ValueError(f"layout desconhecido: {layout!r}. Use um de {sorted(LAYOUTS)}")
    try:
        texto = conteudo.decode(codificacao)
    except UnicodeDecodeError as erro:
        return {"ok": False, "erros": [{"linha": 0, "erro": f"não decodifica em {codificacao}: {erro}"}], "registros": []}

    erros: list[dict] = []
    registros_lidos: list[dict] = []
    for numero, linha in enumerate((l for l in texto.splitlines() if l), start=1):
        identificador = linha[:3].strip()
        registro = camada.REGISTROS.get(identificador)
        if registro is None:
            erros.append({"linha": numero, "erro": f"registro desconhecido: {identificador!r}"})
            continue
        if len(linha) != registro.tamanho:
            erros.append({"linha": numero, "registro": identificador,
                         "erro": f"{len(linha)} posições, esperava {registro.tamanho}"})
            continue
        try:
            valores = ler(linha, registro)
        except ErroEdi as erro:
            erros.append({"linha": numero, "registro": identificador, "erro": str(erro)})
            continue
        for campo in registro.campos:
            if campo.status == "M" and valores.get(campo.nome) is None:
                erros.append({"linha": numero, "registro": identificador, "campo": campo.nome,
                             "erro": "campo obrigatório vazio"})
        registros_lidos.append({
            "linha": numero, "registro": identificador,
            "valores": {nome: (str(valor) if valor is not None else None) for nome, valor in valores.items()},
        })
    return {"ok": not erros, "erros": erros, "registros": registros_lidos}


__all__ = ["codigos", "listar_parceiros", "criar_parceiro", "atualizar_parceiro", "gerar_ocoren", "validar_arquivo"]
