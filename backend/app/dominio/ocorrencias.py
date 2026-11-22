"""Aprofundamento de ocorrências por voz (domínio puro).

Ao registrar uma ocorrência, o agente não para no "registrei": faz as perguntas do tipo, uma de cada
vez, e o CCO recebe o quadro completo. Em acidente, a segurança vem primeiro (feridos → 192/193).
"""
import re
from typing import Optional

from .contingencia import normalizar

# tipo -> [(campo, pergunta falada)], na ordem em que o agente pergunta
PERGUNTAS: dict[str, list[tuple[str, str]]] = {
    "acidente": [
        ("feridos", "Antes de tudo: tem alguém ferido?"),
        ("envolvido", "O seu caminhão se envolveu ou o acidente foi com outro veículo?"),
        ("consegue_seguir", "Você e a carga estão bem? Dá pra seguir viagem?"),
        ("local", "Onde você tá exatamente? Rodovia e quilômetro, se souber."),
    ],
    "avaria": [
        ("o_que", "O que aconteceu com o caminhão?"),
        ("consegue_seguir", "Dá pra seguir ou precisa de socorro mecânico?"),
        ("carga", "A carga foi afetada?"),
    ],
    "atraso": [
        ("quanto", "Quanto tempo de atraso, mais ou menos?"),
        ("motivo", "O que tá causando o atraso?"),
    ],
    "fila": [
        ("quantos", "Quantos caminhões tem na sua frente?"),
        ("previsao", "A portaria deu alguma previsão?"),
    ],
    "doca_ocupada": [
        ("previsao", "Disseram quando a doca libera?"),
        ("outra_doca", "Tem outra doca livre ou só essa?"),
    ],
    "documento": [
        ("qual", "Qual documento pediram?"),
        ("quem", "Quem pediu? A portaria ou o recebimento?"),
    ],
    "recusa": [
        ("motivo", "Qual o motivo que deram pra recusar a carga?"),
        ("quem", "Quem recusou? Me passa o nome se souber."),
    ],
    "outro": [
        ("detalhe", "Me conta um pouco mais: o que aconteceu?"),
    ],
}
SIM_NAO = {"feridos", "consegue_seguir", "outra_doca"}
ROTULO = {
    "feridos": "feridos", "envolvido": "envolvimento", "consegue_seguir": "consegue seguir", "local": "local",
    "o_que": "o que houve", "carga": "carga", "quanto": "atraso", "motivo": "motivo", "quantos": "caminhões na frente",
    "previsao": "previsão", "outra_doca": "outra doca", "qual": "documento", "quem": "quem", "detalhe": "detalhe",
}


def campos(tipo: str) -> list[str]:
    return [c for c, _ in PERGUNTAS.get(tipo, PERGUNTAS["outro"])]


def proxima(tipo: str, faltantes: list[str]) -> Optional[str]:
    """Próxima pergunta a fazer (uma por vez), ou None se já tem tudo."""
    for campo, pergunta in PERGUNTAS.get(tipo, PERGUNTAS["outro"]):
        if campo in faltantes:
            return pergunta
    return None


def extrair(campo: str, fala: str) -> str:
    """Resposta do motorista para o campo. Sim/não normalizado; o resto fica com as palavras dele."""
    if campo in SIM_NAO:
        t = normalizar(fala)
        if re.search(r"\b(nao|ninguem|nenhum|nada|negativo)\b", t) and not re.search(r"\bsim\b.*\b(ferid|machuc)", t):
            # "não dá pra seguir" → não; "não, ninguém se machucou" → não
            return "não"
        if re.search(r"\b(sim|tem|da|consigo|positivo|isso|ferid|machuc)\b", t):
            return "sim"
    return fala.strip()


def grave(tipo: str, detalhes: dict) -> bool:
    """Acidente com ferido é grave: o agente orienta ligar 192/193 e o CCO recebe alerta crítico."""
    return tipo == "acidente" and detalhes.get("feridos") == "sim"


def resumo(tipo: str, descricao: str, detalhes: dict) -> str:
    partes = [f"{ROTULO.get(k, k)}: {v}" for k, v in detalhes.items()]
    return f"{descricao}" + (f" ({'; '.join(partes)})" if partes else "")
