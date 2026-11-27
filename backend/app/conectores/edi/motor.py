"""Motor de EDI de largura fixa: lê a especificação do layout como dado (`Campo`/`Registro`).

Sem conhecimento de OCOREN nem de qualquer outro layout: isso fica em `layouts/*.py`, que só descrevem
dados. Regras comuns aos dois layouts do RODAR (manual Intelipost 5.0, manual PROCEDA 3.1):

- Todo registro tem o mesmo tamanho fixo (250 na 5.0, 120 na 3.1).
- A (alfanumérico): alinhado à esquerda, completado com espaços. N (numérico): alinhado à direita, com
  zeros à esquerda. Decimais são implícitos (N 13,2 ocupa 15 posições; o valor lógico é dividido por 100).
- Campo vazio: zeros se N, espaços se A.
- M = obrigatório (ausente é erro). C = condicional (ausente é válido; sai vazio).
- Valor maior que o campo é erro, nunca truncamento.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union

TIPOS = ("A", "N")
STATUS = ("M", "C")


@dataclass(frozen=True)
class Campo:
    """Um campo de largura fixa. `pos` é a posição inicial do registro, base 1 (como nos manuais)."""
    nome: str
    pos: int
    tamanho: int
    tipo: str  # "A" | "N"
    decimais: int = 0
    status: str = "M"  # "M" | "C"
    maiuscula: bool = False  # 3.1 exige maiúsculas nos campos A; a 5.0 não

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise ValueError(f"{self.nome}: tipo precisa ser A ou N, recebeu {self.tipo!r}")
        if self.status not in STATUS:
            raise ValueError(f"{self.nome}: status precisa ser M ou C, recebeu {self.status!r}")
        if self.pos < 1 or self.tamanho < 1:
            raise ValueError(f"{self.nome}: pos e tamanho precisam ser >= 1")
        if self.decimais and self.tipo != "N":
            raise ValueError(f"{self.nome}: decimais só vale para campo N")


@dataclass(frozen=True)
class Registro:
    """Um registro do arquivo (000, 540, 542, ...). `maximo=None` quando o manual não limita (ex.: 9999)."""
    id: str
    tamanho: int
    campos: tuple[Campo, ...]
    minimo: int = 1
    maximo: Optional[int] = 1
    por: Optional[str] = None  # id do registro "pai" do qual a ocorrência depende (só documentação)

    def campo(self, nome: str) -> Campo:
        for campo in self.campos:
            if campo.nome == nome:
                return campo
        raise KeyError(f"registro {self.id} não tem campo {nome!r}")


class ErroEdi(ValueError):
    """Valor que não cabe no campo, campo obrigatório ausente, ou registro com tamanho errado."""


def _vazio(campo: Campo) -> str:
    return "0" * campo.tamanho if campo.tipo == "N" else " " * campo.tamanho


def formatar_campo(campo: Campo, valor: Any) -> str:
    """Um valor lógico -> string de `campo.tamanho` posições. Levanta `ErroEdi` em vez de truncar."""
    if valor is None or valor == "":
        if campo.status == "M":
            raise ErroEdi(f"campo obrigatório ausente: {campo.nome}")
        return _vazio(campo)
    if campo.tipo == "N":
        try:
            numero = Decimal(str(valor))
        except InvalidOperation as erro:
            raise ErroEdi(f"{campo.nome}: {valor!r} não é numérico") from erro
        inteiro = int((numero * (10 ** campo.decimais)).to_integral_value())
        if inteiro < 0:
            raise ErroEdi(f"{campo.nome}: valor negativo não é suportado neste layout")
        texto = str(inteiro)
        if len(texto) > campo.tamanho:
            raise ErroEdi(f"{campo.nome}: {valor!r} não cabe em {campo.tamanho} posições (N)")
        return texto.rjust(campo.tamanho, "0")
    texto = str(valor)
    if campo.maiuscula:
        texto = texto.upper()
    if len(texto) > campo.tamanho:
        raise ErroEdi(f"{campo.nome}: {valor!r} não cabe em {campo.tamanho} posições (A)")
    return texto.ljust(campo.tamanho, " ")


def formatar(registro: Registro, valores: dict) -> str:
    """`valores` (nome do campo -> valor lógico) -> linha de `registro.tamanho` posições."""
    linha = "".join(formatar_campo(campo, valores.get(campo.nome)) for campo in registro.campos)
    if len(linha) != registro.tamanho:
        raise ErroEdi(f"registro {registro.id}: formatou {len(linha)} posições, esperava {registro.tamanho}")
    return linha


def ler_campo(linha: str, campo: Campo) -> Optional[Union[str, Decimal]]:
    bruto = linha[campo.pos - 1: campo.pos - 1 + campo.tamanho]
    if campo.tipo == "N":
        # "Campo vazio: zeros se N" só vale para decidir ausência num campo C: um M pode ter 0 como valor
        # real (ex.: o identificador do registro "000"), e não é opcional por definição.
        if campo.status == "C" and not bruto.strip("0 "):
            return None
        try:
            return Decimal(bruto) / (10 ** campo.decimais)
        except InvalidOperation as erro:
            raise ErroEdi(f"{campo.nome}: {bruto!r} não é numérico") from erro
    bruto = bruto.rstrip(" ")
    return bruto or None


def ler(linha: str, registro: Registro) -> dict:
    """Linha de `registro.tamanho` posições -> dict (nome do campo -> valor lógico, ou None se vazio)."""
    if len(linha) != registro.tamanho:
        raise ErroEdi(f"registro {registro.id}: linha com {len(linha)} posições, esperava {registro.tamanho}")
    return {campo.nome: ler_campo(linha, campo) for campo in registro.campos}


def validar_layout(registro: Registro) -> None:
    """Confere que os campos cobrem o registro sem buraco nem sobreposição.

    É o teste mais barato contra o erro mais provável: um erro de digitação na especificação do layout.
    """
    ordenados = sorted(registro.campos, key=lambda campo: campo.pos)
    cursor = 1
    for campo in ordenados:
        if campo.pos != cursor:
            raise ErroEdi(f"registro {registro.id}: campo {campo.nome} começa em {campo.pos}, esperava {cursor}")
        cursor += campo.tamanho
    if cursor - 1 != registro.tamanho:
        raise ErroEdi(f"registro {registro.id}: campos somam {cursor - 1}, registro tem {registro.tamanho}")
