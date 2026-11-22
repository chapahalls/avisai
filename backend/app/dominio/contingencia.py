"""Diálogo de contingência (sem LLM): intenção por palavras-chave + resposta com o estado da rota.

Usado quando não há LLM_API_KEY ou o upstream cai. Cobre os fluxos da demo: chegada, ocorrências,
descarga, perguntas de tempo parado/estadia/doca/CCO e a resposta do recebedor na ligação.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Estado:
    nome: str
    destino: str
    status_rota: str
    tempo_parado: Optional[str] = None  # falado: "1 hora e 20 minutos"
    franquia_restante: Optional[str] = None
    valor: Optional[str] = None  # "R$ 70,00"
    task_status: Optional[str] = None
    tentativas_cco: int = 0
    doca: Optional[str] = None
    previsao: Optional[str] = None
    resumo_recebedor: Optional[str] = None
    ligacao_status: Optional[str] = None
    retirada_pendente: bool = False
    chegada_pendente: bool = False
    ocorrencia_tipo: Optional[str] = None
    ocorrencia_faltantes: Optional[list] = None
    inicial_faltantes: Optional[list] = None
    checkin_faltantes: Optional[list] = None
    pergunta_central: Optional[str] = None


@dataclass(frozen=True)
class Decisao:
    texto: str
    ferramenta: Optional[str] = None
    args: dict = field(default_factory=dict)


def normalizar(t: str) -> str:
    """minúsculas e sem acento, preservando o comprimento (para recortar o texto original)."""
    t = unicodedata.normalize("NFC", t)
    return "".join(unicodedata.normalize("NFD", ch)[0] for ch in t).lower()


def _tem(t: str, *padroes: str) -> bool:
    return any(re.search(p, t) for p in padroes)


PERGUNTA = (r"\?", r"\bquanto", r"\bqual\b", r"\bquando\b", r"\bcade\b", r"\balguma noticia", r"\brespondeu",
            r"\bprevisao\b", r"\bja deu\b", r"\bcomo (ta|esta)\b")

OCORRENCIAS = [  # (tipo, padrões, rótulo falado) — a ordem importa
    ("recusa", (r"recus", r"nao vao receber", r"devolv", r"devoluc"), "recusa da carga"),
    ("doca_ocupada", (r"doca\w* (ta |esta )?(ocupad|chei|lotad)", r"(ocupad|lotad)\w* a doca"), "doca ocupada"),
    ("fila", (r"\bfila\b",), "fila"),
    ("documento", (r"\bnota\b", r"\bnf\b", r"document", r"canhoto", r"\bxml\b"), "documento"),
    ("avaria", (r"pneu", r"quebr", r"avaria", r"furou", r"vazament", r"amass"), "avaria"),
    ("acidente", (r"acident", r"batida", r"bateram"), "acidente"),
    ("atraso", (r"atras",), "atraso"),
]

ROTULOS = {"estado_caminhao": "como tá o caminhão", "carga": "qual a carga que você pegou",
           "status_carga": "como tá a carga", "tempo_viagem": "quanto tempo de viagem", "problemas": "se teve algum problema"}
DURACAO = r"\b(\d+|uma|um|duas|dois|tres|quatro|cinco|seis|sete|oito|nove|dez|meia)\s*(e meia\s*)?(horas?|h\b|minutos?|min\b)"

NUMEROS = {"um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4", "cinco": "5",
           "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10"}


def _status(e: Estado) -> str:
    if not e.tempo_parado:
        return f"Ainda não registrei a chegada em {e.destino}. Quando chegar, é só me falar que chegou."
    return (f"Você tá parado há {e.tempo_parado}. Faltam {e.franquia_restante} de franquia "
            f"e a estadia acumulada tá em {e.valor or 'R$ 0,00'}.")


def _doca(e: Estado) -> str:
    if e.doca or e.resumo_recebedor:
        partes = [f"doca {e.doca}" if e.doca else None, e.previsao]
        dito = ", ".join(p for p in partes if p) or e.resumo_recebedor
        return f"O recebimento disse: {dito}."
    if e.ligacao_status == "nao_atendida":
        return "Liguei pro recebimento e ninguém atendeu. Deixei registrado como prova, e o CCO tá sabendo."
    return "Ainda sem resposta do recebimento. O CCO tá avisado e, se ele não responder, eu ligo pro recebedor."


def _cco(e: Estado) -> str:
    if e.task_status == "pendente":
        return (f"O CCO ainda não respondeu: já foram {e.tentativas_cco} tentativas. "
                "Se passar da terceira sem resposta, eu ligo pro recebimento.")
    if e.task_status == "confirmada":
        return "O CCO assumiu o seu caso e tá tratando com o recebedor."
    if e.task_status == "escalada_recebedor":
        return "O CCO não respondeu, então eu liguei pro recebimento. " + _doca(e)
    if e.task_status == "concluida":
        return "O caso já foi fechado com a descarga."
    return "Ainda não tem caso aberto com o CCO. Eu abro assim que você chegar."


def _restantes(faltantes: list, achados: dict) -> list:
    return [k for k in faltantes if k not in achados]


def _pedir(restantes: list, completo: str) -> str:
    if not restantes:
        return completo
    return "Anotado. E " + " e ".join(ROTULOS[k] for k in restantes) + "?"


def _campos_checkin(fala: str, t: str) -> dict:
    out = {}
    if _tem(t, r"carga", r"inteir", r"intact", r"avari", r"perfeit"):
        out["status_carga"] = "avariada" if _tem(t, r"(?<!sem )avari") else "ok"
    dur = _recorte(fala, t, DURACAO)
    if dur:
        out["tempo_viagem"] = dur
    if _tem(t, r"sem problema", r"nenhum", r"\bnada\b", r"tranquil", r"sem ocorrencia"):
        out["problemas"] = "nenhum"
    elif _tem(t, r"problema", r"\bteve\b"):
        out["problemas"] = fala
    return out


def _campos_inicial(fala: str, t: str) -> dict:
    out = {}
    if _tem(t, r"caminhao", r"tudo certo", r"tudo ok", r"tranquil", r"\bok\b"):
        out["estado_caminhao"] = fala
    if _tem(t, r"carga", r"palete", r"tonelad", r"caixa", r"\bpeguei\b", r"carreguei"):
        out["carga"] = fala
    return out


def _motorista(fala: str, t: str, e: Estado) -> Decisao:
    pergunta = _tem(t, *PERGUNTA)
    from . import documentos  # import local: documentos usa normalizar() deste módulo

    if documentos.eh_pergunta(fala) and (pergunta or _tem(t, r"me (fala|diz|passa)")):
        return Decisao("", "consultar_documento", {"pergunta": fala})  # texto = resposta do documento
    if e.retirada_pendente and _tem(t, r"\bconfirm", r"^\s*sim\b", r"\bpeguei\b", r"\bcarreguei\b", r"\bretirei\b", r"\bcarregado\b"):
        return Decisao("Retirada confirmada. Me conta: como tá o caminhão e qual a carga que você pegou?", "confirmar_retirada")
    if e.chegada_pendente and _tem(t, r"\bconfirm", r"^\s*sim\b", r"\bcheguei\b", r"\bchegamos\b", r"\bisso\b", r"\bpositivo\b"):
        return Decisao("Chegada confirmada. Me conta: como tá a carga, quanto tempo de viagem e se teve algum problema?",
                       "confirmar_chegada")
    if _tem(t, r"descarreg", r"terminou a descarga", r"terminei", r"liberaram", r"ta vazio", r"acabou a descarga"):
        return Decisao("Descarga registrada e estadia encerrada. Boa viagem, parceiro!", "confirmar_descarga")
    relata_problema = any(_tem(t, *p) for _, p, _ in OCORRENCIAS)
    if not pergunta and not relata_problema and _tem(t, r"\bcheguei\b", r"\bchegamos\b", r"\bchegou\b", r"(to|tou|estou) (na|no) (portaria|patio)",
                             r"\bna portaria\b", r"\bno patio\b"):
        return Decisao("Chegada registrada, CCO avisado e estadia contando. Me conta: como tá a carga, "
                       "quanto tempo de viagem e se teve algum problema?", "confirmar_chegada")
    if e.pergunta_central and not pergunta and not any(_tem(t, *p) for _, p, _ in OCORRENCIAS):
        return Decisao("Fechado, passei pra central.", "responder_central", {"resposta": fala})
    if e.checkin_faltantes and not pergunta:
        achados = {k: v for k, v in _campos_checkin(fala, t).items() if k in e.checkin_faltantes}
        if achados:
            return Decisao(_pedir(_restantes(e.checkin_faltantes, achados), "Check-in completo, valeu!"),
                           "registrar_checkin", achados)
    if e.inicial_faltantes and not pergunta:
        achados = {k: v for k, v in _campos_inicial(fala, t).items() if k in e.inicial_faltantes}
        if achados:
            return Decisao(_pedir(_restantes(e.inicial_faltantes, achados), "Relatório inicial completo. Boa viagem!"),
                           "registrar_relatorio_inicial", achados)
    if pergunta:
        if _tem(t, r"\bcco\b", r"\bcentral\b"):
            return Decisao(_cco(e))
        if _tem(t, r"doca", r"recebe", r"previsao", r"noticia"):
            return Decisao(_doca(e))
        if _tem(t, r"tempo", r"parad", r"estadia", r"franquia", r"hora", r"valor", r"quanto"):
            return Decisao(_status(e))
    outro_problema = any(_tem(t, *p) for tp, p, _ in OCORRENCIAS if tp != e.ocorrencia_tipo)
    if e.ocorrencia_faltantes and not pergunta and not outro_problema:
        from . import ocorrencias as roteiro

        campo = e.ocorrencia_faltantes[0]
        valor = roteiro.extrair(campo, fala)
        restantes = e.ocorrencia_faltantes[1:]
        prox = roteiro.proxima(e.ocorrencia_tipo, restantes)
        alerta = ""
        if roteiro.grave(e.ocorrencia_tipo, {campo: valor}):
            alerta = ("Se ainda não ligaram, liga agora pro SAMU no 192 ou pros bombeiros no 193. "
                      "Já alertei o CCO como urgente. ")
        texto = alerta + (f"Anotado. {prox}" if prox else "Anotado, passei tudo pro CCO. Qualquer novidade, me fala.")
        return Decisao(texto, "detalhar_ocorrencia", {campo: valor})
    for tipo, padroes, rotulo in OCORRENCIAS:
        if _tem(t, *padroes):
            from . import ocorrencias as roteiro

            return Decisao(f"Registrei a ocorrência de {rotulo} e o CCO já tá vendo. {roteiro.proxima(tipo, roteiro.campos(tipo))}",
                           "registrar_ocorrencia", {"tipo": tipo, "descricao": fala})
    if _tem(t, r"\boi\b", r"\bola\b", r"bom dia", r"boa tarde", r"boa noite", r"\be ai\b", r"tudo bem"):
        situacao = (f"Você tá parado há {e.tempo_parado} em {e.destino}." if e.tempo_parado
                    else f"Tô acompanhando a sua entrega em {e.destino}.")
        return Decisao(f"E aí, {e.nome}! {situacao} Qualquer coisa, me fala.")
    if pergunta:
        return Decisao(_status(e))
    return Decisao("Não peguei direito. Posso registrar a sua chegada, uma ocorrência como fila ou doca ocupada, "
                   "a descarga, ou te dizer o tempo parado e a estadia.")


def _recorte(fala: str, t: str, padrao: str) -> Optional[str]:  # noqa: F811
    m = re.search(padrao, t)
    return fala[m.start():m.end()].strip() if m else None


def _recebedor(fala: str, t: str) -> Decisao:
    doca = None
    m = re.search(r"doca\s+(\d+|" + "|".join(NUMEROS) + r")\b", t)
    if m:
        doca = NUMEROS.get(m.group(1), m.group(1))
    previsao = (_recorte(fala, t, r"\b(em|daqui)\s+(a\s+)?(uns?\s+|umas?\s+)?(\d+|uma|um|meia|duas|dois)\s+(minutos?|horas?|hora)\b")
                or _recorte(fala, t, r"\b(as|a partir das)\s+\d{1,2}(\s*h(oras?)?|:\d{2})(\d{2})?"))
    nao_recebe = _tem(t, r"nao (recebe|recebemos|vamos receber)", r"so amanha", r"\bamanha\b")
    if nao_recebe:
        previsao = "só amanhã (não recebe hoje)" if "amanha" in t else "não recebe hoje"
    if doca or previsao:
        partes = [f"doca {doca}" if doca else None, previsao]
        args = {"doca": doca, "previsao": previsao, "resumo": fala}
        if nao_recebe:
            args["recebe_hoje"] = False  # aplica a regra da transportadora
        return Decisao(f"Anotado: {', '.join(p for p in partes if p)}. Vou passar pro motorista agora. Obrigada!",
                       "registrar_resposta_recebedor", args)
    return Decisao("Desculpe, é a assistente virtual da transportadora. Qual a previsão de descarga e a doca para o motorista?")


def decidir(papel: str, fala: str, estado: Estado) -> Decisao:
    t = normalizar(fala or "")
    return _recebedor(fala, t) if papel == "recebedor" else _motorista(fala, t, estado)
