"""Documentos da viagem (NF-e e CT-e fictícios) e consulta por voz.

Regra contra alucinação (contexto-produto.md, riscos): número de NF, peso e valores não podem ser
"aproximados". A resposta sai só de campos do documento, cita qual documento foi usado e diz
"não encontrei" quando o campo não existe.
"""
import re
from typing import Any, Optional

from .contingencia import normalizar


def _reais(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def da_rota(r: Any, empresa: str) -> list[dict]:
    """Documentos mock da rota (os mesmos que /api/documents devolve)."""
    peso = int(round(r.carga_t * 1000))
    nfe = {
        "id": f"nfe-{r.nota_fiscal}", "kind": "NF-e", "title": f"NF-e {r.nota_fiscal}", "number": r.nota_fiscal,
        "issuer": empresa, "recipient": r.recebedor_empresa, "weightKg": peso, "items": r.carga_descricao,
        "valueBRL": 84230.50, "fileUri": None, "mock": True,
        "campos": {"numero": r.nota_fiscal, "emitente": empresa, "destinatario": r.recebedor_empresa,
                   "peso_kg": peso, "itens": r.carga_descricao, "valor": 84230.50,
                   "chave": "3526 1104 8291 3000 0155 5500 1000 4829 1310 0048 2913"},
    }
    cte = {
        "id": "cte-000771204", "kind": "CT-e", "title": "CT-e 000.771.204", "number": "000.771.204",
        "carrier": empresa, "plate": r.placa, "freightBRL": 3120.00, "fileUri": None, "mock": True,
        "campos": {"numero": "000.771.204", "transportadora": empresa, "placa": r.placa, "frete": 3120.00,
                   "nfe_referenciada": r.nota_fiscal},
    }
    return [nfe, cte]


# (campo, padrões, rótulo falado). A ordem importa: o primeiro que casar vence.
CAMPOS = {
    "NF-e": [
        ("chave", (r"chave",), "a chave de acesso é"),
        ("valor", (r"\bvalor\b", r"\bvale\b", r"preco", r"quanto custa"), "o valor é"),
        ("peso_kg", (r"\bpeso\b", r"quilo", r"\bkg\b", r"tonelad"), "o peso é"),
        ("destinatario", (r"pra quem", r"para quem", r"destinat", r"\bcliente\b", r"recebedor"), "o destinatário é"),
        ("emitente", (r"emitente", r"quem emitiu", r"remetente", r"quem mandou"), "o emitente é"),
        ("itens", (r"o que tem", r"\bitens\b", r"produto", r"mercadoria", r"\bcarga\b", r"palete"), "a carga é"),
        ("numero", (r"numero", r"\bn[ºo°]\b", r"qual (e )?a nota"), "o número é"),
    ],
    "CT-e": [
        ("frete", (r"frete",), "o frete é"),
        ("placa", (r"placa",), "a placa é"),
        ("transportadora", (r"transportadora", r"quem transporta"), "a transportadora é"),
        ("numero", (r"numero", r"\bn[ºo°]\b"), "o número é"),
    ],
}
DOC_CTE = (r"\bct-?e\b", r"conhecimento", r"frete", r"\btransporte\b")
DOC_QUALQUER = (r"\bnota\b", r"\bnf\b", r"\bnf-?e\b", r"nota fiscal", r"danfe", r"documento", r"chave de acesso") + DOC_CTE


def _tem(t: str, pads) -> bool:
    return any(re.search(p, t) for p in pads)


def eh_pergunta(fala: str) -> bool:
    """A fala é uma pergunta sobre os documentos da viagem?"""
    return _tem(normalizar(fala or ""), DOC_QUALQUER)


def _formatar(campo: str, v: Any) -> str:
    if campo == "peso_kg":
        kg = f"{int(v):,}".replace(",", ".")
        return f"{kg} kg ({v / 1000:g} toneladas)"
    if campo in ("valor", "frete"):
        return _reais(v)
    return str(v)


def consultar(docs: list[dict], pergunta: str, documento: Optional[str] = None) -> dict:
    """Procura o campo pedido. Nunca inventa: sem campo, devolve encontrado=False."""
    t = normalizar(pergunta or "")
    if _tem(t, (r"\bquais\b", r"\blista\b", r"\bnome", r"\btem quais\b", r"disponiveis")) and _tem(t, DOC_QUALQUER):
        titulos = " e ".join(d["title"] for d in docs)
        return {
            "encontrado": True,
            "documento": None,
            "campo": "documentos",
            "valor": titulos,
            "resposta": f"Os documentos disponíveis são: {titulos}.",
        }
    preferido = documento or ("CT-e" if _tem(t, DOC_CTE) else "NF-e")
    ordem = sorted(docs, key=lambda d: d["kind"] != preferido)
    for d in ordem:
        for campo, pads, rotulo in CAMPOS.get(d["kind"], []):
            if _tem(t, pads) and campo in d["campos"]:
                valor = _formatar(campo, d["campos"][campo])
                artigo = "Pelo" if d["kind"] == "CT-e" else "Pela"  # o CT-e, a NF-e
                return {"encontrado": True, "documento": d["title"], "campo": campo, "valor": valor,
                        "resposta": f"{artigo} {d['title']}, {rotulo} {valor}."}
        if d["kind"] == preferido and documento:
            break
    titulos = " e ".join(d["title"] for d in docs)
    return {"encontrado": False, "documento": None, "campo": None, "valor": None,
            "resposta": f"Não encontrei isso nos documentos da viagem ({titulos})."}
