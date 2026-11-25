"""Comandos do app do motorista por voz (domínio puro).

O agente interpreta a fala e o backend manda ao app só a intenção autorizada, pelo canal
`acao_cliente` do WebSocket. O app nunca age a partir da transcrição.

Contrato com o app (`acao_cliente`):
    {"rota_id": int, "acao": "open_screen", "tela": "inicio|mapa|documentos|mensagens|fila"}
    {"rota_id": int, "acao": "open_document", "documento": "NF-e" | "CT-e" | nome do anexo}
    {"rota_id": int, "acao": "go_back"}
    {"rota_id": int, "acao": "end_voice"}   o app encerra a conversa depois que o agente se despede
    {"rota_id": int, "acao": "logout"}      só depois de o motorista confirmar
    {"rota_id": int, "acao": "open_navigation"}  rota até o destino no app de mapas
    {"rota_id": int, "acao": "start_gps"}

Documentos e mensagens pedem leitura: com o caminhão andando, o app só abre quando ele parar
(o agente avisa isso em vez de dizer "abrindo").
"""
import re
from dataclasses import dataclass
from typing import Optional

from .contingencia import normalizar

TELAS = ("inicio", "mapa", "documentos", "mensagens", "fila")
ACOES = ("abrir_tela", "abrir_documento", "voltar", "encerrar_conversa", "sair_da_conta", "navegar", "ligar_gps")
TELAS_DE_LEITURA = ("documentos", "mensagens")
STATUS_EM_MOVIMENTO = ("em_transito", "aproximando")

ACAO_CLIENTE = {
    "abrir_tela": "open_screen",
    "abrir_documento": "open_document",
    "voltar": "go_back",
    "encerrar_conversa": "end_voice",
    "sair_da_conta": "logout",
    "navegar": "open_navigation",
    "ligar_gps": "start_gps",
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


def exige_parado(cmd: Comando) -> bool:
    """Telas de leitura: com o caminhão andando, o app só abre quando ele parar."""
    return cmd.acao == "abrir_documento" or (cmd.acao == "abrir_tela" and cmd.tela in TELAS_DE_LEITURA)


def fala_confirmacao(cmd: Comando, status_rota: Optional[str] = None) -> str:
    if status_rota in STATUS_EM_MOVIMENTO and exige_parado(cmd):
        return "Com o caminhão andando eu não abro isso na tela. Abro assim que você parar; se quiser, eu te falo o que precisa."
    if cmd.acao == "navegar":
        return "Abrindo a rota no mapa do celular."
    if cmd.acao == "ligar_gps":
        return "GPS ligado."
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

_ABRIR = r"\b(abr\w*|mostr\w*|ver|veja|exib\w*|(mud|troc|pass)\w* (pras?|para|pros?)|ir (pras?|para|pros?|ao|aos|as?|nos?|nas?)|vai (pras?|para|pros?)|vamos (pras?|para|pros?)|leva\w* (pras?|para|pros?)|entr\w* (em|no|na)|open|show|go to)\b"
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
_NAVEGAR = (r"\bme lev\w*\b|\bleva eu\b|\bnaveg\w* (ate|pras?|pros?|para)\b|\bcomo (eu )?chego\b"
            r"|\babr\w* (o )?(google maps|waze|navegacao|navegador)\b|\b(inici|comec)\w* (a )?navegacao\b")
_LIGAR_GPS = r"\b(lig|ativ|liga|ative|ativa)\w* (o |a )?(gps|localizacao|rastreamento)\b"
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
    if re.search(_NAVEGAR, t) and "?" not in fala.replace("como chego", ""):
        return Comando("navegar")
    if re.search(_LIGAR_GPS, t):
        return Comando("ligar_gps")
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


# ---------- mensagem livre ao CCO e "repete" ----------

_MSG_CCO = re.compile(
    r"\b(?:avis\w*|fal\w*|diz\w*|manda\w*|mand\w*(?: uma)? (?:mensagem|recado)|deixa\w*(?: um)? recado)"
    r" (?:pro|pra|para o|ao|o)? ?(?:cco|central|operador|operacao)\b[,:]?\s*(?:(?:dizendo|falando|avisando)\s+)?(?:que\s+)?(.+)"
)
_REPETIR = r"\b(repet\w*|o que (voce|vc|tu) (disse|falou)|nao (entendi|ouvi)|como e que e)\b"


def mensagem_cco(fala: str) -> Optional[str]:
    """ "avisa o CCO que vou parar pra almoçar" → "vou parar pra almoçar". Sem texto, None."""
    t = normalizar(fala or "")
    m = _MSG_CCO.search(t)
    if not m:
        return None
    inicio = m.start(1)  # normalizar preserva o comprimento: recorta a fala original
    texto = (fala or "")[inicio:].strip(" ,.:;")
    return texto or None


_RECADO_VAZIO = re.compile(
    r"^\s*(?:(?:me )?(?:avis\w*|fal\w*|diz\w*|manda\w*|mand\w*(?: uma)? (?:mensagem|recado)|deixa\w*(?: um)? recado))"
    r" (?:pro|pra|para o|ao|o)? ?(?:cco|central|operador|operacao)\s*[.!]?\s*$"
)


def pede_recado_vazio(fala: str) -> bool:
    """'manda pro CCO' sem dizer o quê: o agente pergunta o recado."""
    return bool(_RECADO_VAZIO.search(normalizar(fala or "")))


def pede_repetir(fala: str) -> bool:
    return bool(re.search(_REPETIR, normalizar(fala or "")))


def falar_avisos(avisos: list[str]) -> str:
    if not avisos:
        return "Não tenho aviso recente pra você."
    if len(avisos) == 1:
        return f"O último aviso foi: {avisos[0]}"
    return "Os últimos avisos foram: " + " Depois: ".join(avisos)
