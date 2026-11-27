"""Chave de acesso da NF-e (44 dígitos) e o dígito verificador módulo 11.

O 542 (OCOREN 5.0) e o 342 (3.1) pedem CNPJ, série e número da nota, que no RODAR vêm só da chave de
NF-e (`Rota.nfe_chave`), não de um campo próprio — ver seção 5 do docs/edi/ocoren-integracao.md.
"""
from dataclasses import dataclass

_PESOS = (2, 3, 4, 5, 6, 7, 8, 9)
TAMANHO_CHAVE = 44


def digito_verificador(chave_43: str) -> int:
    """Módulo 11 da NF-e: pesos 2-9 da direita para a esquerda; resto 0 ou 1 -> DV 0."""
    if len(chave_43) != TAMANHO_CHAVE - 1 or not chave_43.isdigit():
        raise ValueError(f"esperava 43 dígitos para calcular o DV, recebeu {chave_43!r}")
    total = sum(int(digito) * _PESOS[indice % len(_PESOS)] for indice, digito in enumerate(reversed(chave_43)))
    resto = total % 11
    return 0 if resto in (0, 1) else 11 - resto


@dataclass(frozen=True)
class ChaveNFe:
    cuf: str
    aamm: str
    cnpj: str
    modelo: str
    serie: str
    numero: str
    tipo_emissao: str
    codigo_numerico: str
    dv: str

    @classmethod
    def parse(cls, chave: str) -> "ChaveNFe":
        digitos = "".join(caractere for caractere in chave if caractere.isdigit())
        if len(digitos) != TAMANHO_CHAVE:
            raise ValueError(f"chave de NF-e precisa ter {TAMANHO_CHAVE} dígitos, recebeu {len(digitos)}")
        instancia = cls(
            cuf=digitos[0:2], aamm=digitos[2:6], cnpj=digitos[6:20], modelo=digitos[20:22],
            serie=digitos[22:25], numero=digitos[25:34], tipo_emissao=digitos[34:35],
            codigo_numerico=digitos[35:43], dv=digitos[43:44],
        )
        if digito_verificador(digitos[:43]) != int(instancia.dv):
            raise ValueError("dígito verificador da chave de NF-e inválido")
        return instancia


def gerar_chave(*, cuf: str, aamm: str, cnpj: str, modelo: str = "55", serie: str, numero: str,
                 tipo_emissao: str = "1", codigo_numerico: str) -> str:
    """Monta uma chave de 44 dígitos (com DV válido) a partir das partes — usada no seed, com dados fictícios."""
    base = (f"{cuf:>02}{aamm:>04}{cnpj:>014}{modelo:>02}{serie:>03}{numero:>09}{tipo_emissao:>01}"
            f"{codigo_numerico:>08}")
    if len(base) != TAMANHO_CHAVE - 1:
        raise ValueError(f"partes somaram {len(base)} dígitos, esperava {TAMANHO_CHAVE - 1}")
    return base + str(digito_verificador(base))
