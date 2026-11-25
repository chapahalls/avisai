"""O que vai para o sistema tem de ter saído da boca do motorista (domínio puro).

O LLM às vezes "completa" um relatório com dados da rota que o motorista não disse
("caminhão pronto, 28 paletes") só porque estão no prompt. Antes de gravar, cada campo
precisa casar com a fala da vez: por palavra parecida ou por um assunto típico do campo.
"""
import re
from typing import Optional

from .contingencia import normalizar

_PALAVRAS_VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "com", "pra", "para", "por", "que", "ta", "esta", "tá", "foi", "ser", "sao", "eh", "ja", "mais",
}

# Assuntos que, ditos pelo motorista, sustentam o campo mesmo com o LLM reescrevendo a frase.
ASSUNTO = {
    "estado_caminhao": r"\bcaminh\w*\b|\bpneu|\bmotor\b|\bfreio|\btudo (certo|ok|em ordem|tranquilo)\b|\bde boa\b|\bsem problema",
    "carga": r"\bpalet|\bcaixa|\btonel|\bbebid|\bsaco|\bgranel\b|\bkg\b|\b\d+ ?(t|ton)\b|\bcarga (e|eh|sao|de)\b",
    "status_carga": r"\bcarga\b|\bintact|\binteir|\bavari|\bmolh|\bamass",
    "tempo_viagem": r"\d|\bhora|\bminut|\bmeia\b",
    "problemas": r"\bproblem|\bnada\b|\bnenhum|\btranquil|\bsem ocorr|\bfila\b|\bpneu|\batras",
}


def _raizes(texto: str) -> set[str]:
    palavras = re.findall(r"[a-z0-9]+", normalizar(texto or ""))
    return {p[:3] for p in palavras if len(p) >= 3 and p not in _PALAVRAS_VAZIAS}


def fundamentado(campo: str, valor: str, fala: Optional[str]) -> bool:
    """O valor do campo saiu da fala? Sem fala para comparar, não dá para afirmar: aceita."""
    if not fala or not fala.strip():
        return True
    t = normalizar(fala)
    if campo in ASSUNTO and re.search(ASSUNTO[campo], t):
        return True
    return bool(_raizes(valor) & _raizes(fala))


def so_o_que_ele_disse(campos: dict, fala: Optional[str]) -> tuple[dict, list[str]]:
    """Separa os campos sustentados pela fala dos que o LLM inventou."""
    aceitos, recusados = {}, []
    for k, v in (campos or {}).items():
        if v in (None, ""):
            continue
        if fundamentado(k, str(v), fala):
            aceitos[k] = v
        else:
            recusados.append(k)
    return aceitos, recusados
