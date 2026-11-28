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


# O que a própria descrição da ocorrência já responde ("furou o pneu" é o "o que aconteceu").
RESPONDIDO_PELA_DESCRICAO = {"avaria": "o_que", "outro": "detalhe"}


def detalhes_iniciais(tipo: str, descricao: str) -> dict:
    campo = RESPONDIDO_PELA_DESCRICAO.get(tipo)
    return {campo: descricao.strip()} if campo and (descricao or "").strip() else {}


def campos_a_perguntar(tipo: str, descricao: str) -> list[str]:
    ja = detalhes_iniciais(tipo, descricao)
    return [c for c in campos(tipo) if c not in ja]


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


# Campos que dá para reconhecer mesmo quando não foram a pergunta da vez
# ("a carga tá inteira, consigo seguir" responde carga e consegue_seguir de uma vez).
_DETECTA = {
    "consegue_seguir": r"\b(consigo|da pra|posso|vou|pode) seguir\b|\bseguir viagem\b|\b(nao (consigo|da|posso) (pra )?seguir)\b"
                       r"|\bpreciso de (socorro|guincho|mecanico)\b",
    "carga": r"\bcarga (ta |esta |ficou |tá )?(inteira|ok|boa|intacta|de boa|perfeita|avariad\w*|molhad\w*|danificad\w*|caiu|tombou|amassad\w*)",
    "feridos": r"\b(ninguem|nenhum|ninguém) (se )?(ferid\w*|machuc\w*)|\b(tem|ha) (gente |alguem )?(ferid\w*|machucad\w*)",
    "local": r"\b(br|sp|mg|pr|rj)[- ]?\d{2,3}\b|\b(km|quilometro) \d+",
}


def detectar(faltantes: list[str], fala: str) -> dict:
    """Só os campos que a fala responde claramente (sem chutar o primeiro)."""
    t = normalizar(fala or "")
    return {c: (extrair(c, fala) if c in SIM_NAO else fala.strip())
            for c in faltantes if _DETECTA.get(c) and re.search(_DETECTA[c], t)}


def extrair_varios(faltantes: list[str], fala: str) -> dict:
    """A resposta vale para o 1º campo que falta e para qualquer outro que a fala responda claramente."""
    if not faltantes:
        return {}
    t = normalizar(fala)
    achados = {faltantes[0]: extrair(faltantes[0], fala)}
    for campo in faltantes[1:]:
        padrao = _DETECTA.get(campo)
        if padrao and re.search(padrao, t):
            achados[campo] = extrair(campo, fala) if campo in SIM_NAO else fala.strip()
    return achados


# Enquanto o caminhão ainda está na estrada (em_transito, antes da geocerca de aproximação),
# não existe fila de caminhões num recebedor: só dá pra fazer fila na doca depois de chegar lá.
# "Trânsito parado" e "fila de caminhões" são falas parecidas e o LLM de verdade às vezes
# classifica a primeira como `fila` — e avisar o recebedor do atraso não pode depender só da
# classificação livre do modelo. Corrige pelo estado da rota, que é determinístico, em vez de
# confiar só no que o modelo escolheu.
def corrigir_tipo_por_estado(tipo: str, status_rota: str) -> str:
    if tipo == "fila" and status_rota == "em_transito":
        return "atraso"
    return tipo


def grave(tipo: str, detalhes: dict) -> bool:
    """Acidente com ferido é grave: o agente orienta ligar 192/193 e o CCO recebe alerta crítico."""
    return tipo == "acidente" and detalhes.get("feridos") == "sim"


def resumo(tipo: str, descricao: str, detalhes: dict) -> str:
    partes = [f"{ROTULO.get(k, k)}: {v}" for k, v in detalhes.items()]
    return f"{descricao}" + (f" ({'; '.join(partes)})" if partes else "")
