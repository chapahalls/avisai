"""Comandos do app do motorista por voz (domínio puro).

O agente interpreta a fala e o backend manda ao app só a intenção autorizada, pelo canal
`acao_cliente` do WebSocket. O app nunca age a partir da transcrição.

Contrato com o app (`acao_cliente`):
    {"rota_id": int, "acao": "open_screen", "tela": "inicio|mapa|documentos|mensagens|fila"}
    {"rota_id": int, "acao": "open_document", "documento": "NF-e" | "CT-e" | nome do anexo}
    {"rota_id": int, "acao": "go_back"}
    {"rota_id": int, "acao": "end_voice"}   o app encerra a conversa depois que o agente se despede
    {"rota_id": int, "acao": "logout"}      só depois de o motorista confirmar
"""
import re
from dataclasses import dataclass
from typing import Optional

from .contingencia import normalizar

TELAS = ("inicio", "mapa", "documentos", "mensagens", "fila")
ACOES = ("abrir_tela", "abrir_documento", "voltar", "encerrar_conversa", "sair_da_conta")

ACAO_CLIENTE = {
    "abrir_tela": "open_screen",
    "abrir_documento": "open_document",
    "voltar": "go_back",
    "encerrar_conversa": "end_voice",
    "sair_da_conta": "logout",
}

FALA_TELA = {
    "inicio": "Voltando pro início.",
    "mapa": "Abrindo o mapa.",
    "documentos": "Abrindo os documentos.",
    "mensagens": "Abrindo as mensagens.",
    "fila": "Abrindo a fila do recebedor.",
}

PEDIR_CONFIRMACAO_SAIR = "Quer mesmo sair da conta? Diga: confirmo, sair da conta."


@dataclass(frozen=True)
class Comando:
    acao: str
    tela: Optional[str] = None
    documento: Optional[str] = None
    confirmado: bool = False

    def args(self) -> dict:
        a: dict = {"acao": self.acao}
        if self.tela:
            a["tela"] = self.tela
        if self.documento:
            a["documento"] = self.documento
        if self.confirmado:
            a["confirmado"] = True
        return a


def validar(args: dict) -> tuple[Optional[Comando], Optional[str]]:
    """Confere os argumentos vindos do LLM. Devolve (comando, erro)."""
    acao = str(args.get("acao") or "").strip()
    if acao not in ACOES:
        return None, f"Ação desconhecida: {acao or 'vazia'}."
    if acao == "abrir_tela":
        tela = str(args.get("tela") or "").strip()
        if tela not in TELAS:
            return None, f"Tela desconhecida: {tela or 'vazia'}. Telas: {', '.join(TELAS)}."
        return Comando(acao, tela=tela), None
    if acao == "abrir_documento":
        doc = str(args.get("documento") or "").strip()
        if not doc:
            return None, "Diga qual documento abrir (NF-e, CT-e ou o nome do anexo)."
        return Comando(acao, documento=_documento_canonico(doc)), None
    if acao == "sair_da_conta":
        return Comando(acao, confirmado=bool(args.get("confirmado"))), None
    return Comando(acao), None


def payload_cliente(rota_id: int, cmd: Comando) -> dict:
    p: dict = {"rota_id": rota_id, "acao": ACAO_CLIENTE[cmd.acao]}
    if cmd.tela:
        p["tela"] = cmd.tela
    if cmd.documento:
        p["documento"] = cmd.documento
    return p


def fala_confirmacao(cmd: Comando) -> str:
    if cmd.acao == "abrir_tela":
        return FALA_TELA[cmd.tela or "inicio"]
    if cmd.acao == "abrir_documento":
        return f"Abrindo {_falar_documento(cmd.documento)}."
    if cmd.acao == "voltar":
        return "Voltando."
    if cmd.acao == "encerrar_conversa":
        return "Fechado, encerrando a conversa. Quando precisar, é só dizer: Ei, AvisAI."
    return "Saindo da conta. Até mais!"


def _documento_canonico(doc: str) -> str:
    t = normalizar(doc)
    if re.search(r"\bnf-?e\b|\bnota\b|\bnf\b|danfe|invoice", t):
        return "NF-e"
    if re.search(r"\bct-?e\b|conhecimento|dacte", t):
        return "CT-e"
    if re.search(r"\bmdf-?e\b|manifesto", t):
        return "MDF-e"
    return doc.strip()


def _falar_documento(doc: Optional[str]) -> str:
    return {"NF-e": "a nota fiscal", "CT-e": "o CT-e", "MDF-e": "o manifesto"}.get(doc or "", f"o documento {doc}")


# ---------- contingência (sem LLM): intenção por palavras-chave ----------

_ABRIR = r"\b(abr\w*|mostr\w*|ver|veja|exib\w*|ir (pras?|para|pros?|ao|aos|as?|nos?|nas?)|vai (pras?|para|pros?)|vamos (pras?|para|pros?)|leva\w* (pras?|para|pros?)|entr\w* (em|no|na)|open|show|go to)\b"
_TELAS_RE = [  # a ordem importa: "fila do recebedor" antes de "mensagens"
    ("fila", r"\bfila (do|no|da) (recebedor|recebimento|doca|descarga)\b|\bfila\b(?!.*\bsincroniza)|\bdoca\b"),
    ("mensagens", r"\bmensage(m|ns)\b|\bchat\b|\bconversa com (o )?cco\b|\bsincroniza\w*|\boutbox\b"),
    ("mapa", r"\bmapa\b|\bnavega\w*\b|\btrajeto\b|\brota\b"),
    ("documentos", r"\bdocumento\w*\b|\barquivo\w*\b|\banexo\w*\b"),
    ("inicio", r"\binicio\b|\btela (principal|inicial)\b|\bhome\b|\bviagem\b"),
]
_DOC_RE = r"\bnota( fiscal)?\b|\bnf-?e\b|\bnf\b|\bdanfe\b|\bct-?e\b|\bconhecimento\b|\bdacte\b|\bmanifesto\b|\bmdf-?e\b"
_CAMPO_DOC = r"\b(peso|valor|numero|chave|destinatario|emitente|frete|placa|ite(m|ns)|quanto|qual|quais)\b"
_ENCERRAR = (
    r"\b(encerr|finaliz|termin|deslig|fech|para|pare)\w* (a |essa |esta )?(conversa|ligacao|chamada|sessao|voz)\b",
    r"\b(tchau|ate mais|ate logo|falou)\b.*\bavis\s?a?\s?a?i\b",
    r"\bpode (desligar|encerrar)\b",
)
_SAIR = r"\b(sair|saia|sai) da (minha )?conta\b|\bfaz(er)? logout\b|\bdeslog\w*\b|\blog ?out\b"
_CONFIRMA_SAIR = r"\bconfirm\w*\b.*\b(sair|logout|deslog)"


def interpretar(fala: str) -> Optional[Comando]:
    """Fala → comando do app, quando for claramente um pedido de navegação ou de encerrar.
    Perguntas ("quanto falta pro destino no mapa?") ficam com o diálogo normal."""
    t = normalizar(fala or "")
    if not t.strip():
        return None
    if re.search(_CONFIRMA_SAIR, t):
        return Comando("sair_da_conta", confirmado=True)
    if re.search(_SAIR, t):
        return Comando("sair_da_conta")
    if any(re.search(p, t) for p in _ENCERRAR):
        return Comando("encerrar_conversa")
    if re.search(r"\bvolt\w*\b", t) and not re.search(_ABRIR, t) and not any(re.search(p, t) for _, p in _TELAS_RE):
        return Comando("voltar")
    pede = re.search(_ABRIR, t) or re.search(r"\bvolt\w* (pras?|para|pros?|ao|as?)\b", t)
    if not pede or "?" in fala:
        return None
    doc = re.search(_DOC_RE, t)
    if doc and re.search(_CAMPO_DOC, t):
        return None  # "mostra o peso da nota" é pergunta: consultar_documento responde
    if doc:
        return Comando("abrir_documento", documento=_documento_canonico(doc.group(0)))
    for tela, padrao in _TELAS_RE:
        if re.search(padrao, t):
            return Comando("abrir_tela", tela=tela)
    return None
