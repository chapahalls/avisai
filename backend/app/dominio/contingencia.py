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
    ultimos_avisos: Optional[list] = None
    ultima_fala_agente: Optional[str] = None  # o que o agente acabou de dizer (contexto do "sim"/"não")


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

def classificar_ocorrencia(texto: str) -> Optional[str]:
    """Tipo da ocorrência pelas palavras ("furou o pneu" → avaria). None se não reconhecer."""
    t = normalizar(texto or "")
    for tipo, padroes, _ in OCORRENCIAS:
        if _tem(t, *padroes):
            return tipo
    return None


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

    from . import comandos_app

    # Antes das outras intenções: "quero sair da conta" não é "quero sair" (iniciar viagem).
    cmd = comandos_app.interpretar(fala)
    if cmd:
        if cmd.acao == "sair_da_conta" and not cmd.confirmado:
            return Decisao(comandos_app.PEDIR_CONFIRMACAO_SAIR)
        return Decisao(comandos_app.fala_confirmacao(cmd, e.status_rota), "comandar_app", cmd.args())
    pendente = _central_a_confirmar(e.ultima_fala_agente) if e.pergunta_central else None
    if pendente is not None:
        if _tem(t, *SIM):
            # "sim, tá lacrada" diz mais que o "certo" de antes: manda a fala completa.
            resto = re.sub(SIM[0], "", t).strip(" ,.!")
            resposta = fala.strip() if len(re.findall(r"\w+", resto)) >= 2 else pendente
            return Decisao("Fechado, passei pra central.", "responder_central", {"resposta": resposta})
        if _tem(t, *NAO):
            return Decisao("Beleza. Qual é a resposta pra central, então?")
    if _tem(t, r"\b(o que|oque) (voce|vc|tu) (faz|pode fazer|sabe fazer|consegue)\b", r"\bcomo (voce|vc) (funciona|me ajuda)\b",
            r"^\s*(me )?ajuda\b"):
        return Decisao("Eu cuido da sua entrega por voz: registro chegada, ocorrência e descarga, conto a estadia, "
                       "falo com o CCO e abro as telas pra você. É só falar.")
    if _tem(t, r"\b(o que eu perdi|teve (algum |alguma )?(aviso|novidade)|alguma novidade)\b"):
        return Decisao(comandos_app.falar_avisos((e.ultimos_avisos or [])[-2:]))
    if comandos_app.pede_repetir(fala):
        if e.ultima_fala_agente:
            return Decisao(e.ultima_fala_agente)
        return Decisao(comandos_app.falar_avisos((e.ultimos_avisos or [])[-2:]))
    if (e.ultima_fala_agente or "") == PERGUNTA_RECADO and not pergunta and not any(_tem(t, *p) for _, p, _ in OCORRENCIAS):
        texto_recado = fala.strip(" .")
        return Decisao(f"Mandei pro CCO: {texto_recado}. Te aviso quando responderem.", "enviar_mensagem_cco",
                       {"texto": texto_recado})
    if comandos_app.pede_recado_vazio(fala):
        return Decisao(PERGUNTA_RECADO)
    recado = comandos_app.mensagem_cco(fala)
    if recado and not any(_tem(normalizar(recado), *p) for _, p, _ in OCORRENCIAS):
        return Decisao(f"Mandei pro CCO: {recado}. Te aviso quando responderem.", "enviar_mensagem_cco", {"texto": recado})

    if not pergunta and _tem(
        t,
        r"\b(inici|comec|sair|partir)\w*(?:\s+a)?\s+(?:viagem|rota)\b",
        r"\bquero\s+(?:viajar|sair)\b",
    ) or (e.status_rota in ("planejada", "na_origem") and _tem(
        t, r"\bpeguei a carga\b", r"\bcarreguei\b", r"\b(ja )?(to|tou|estou|ta|esta) carregad", r"\bcarga (ta |esta )?(no caminhao|carregada)\b",
        r"\b(partiu|bora|vamo(s)? nessa|pe na estrada)\b",
    )):
        if e.status_rota in ("planejada", "na_origem"):
            return Decisao(
                "Retirada registrada, viagem iniciada. Me conta: como tá o caminhão e qual a carga que você pegou?",
                "confirmar_retirada",
                {"observacao": fala},
            )
        if e.status_rota in ("em_transito", "aproximando"):
            return Decisao("A viagem já está em andamento.")
        return Decisao("Essa viagem já foi concluída. O CCO precisa atribuir uma nova rota antes de iniciar outra.")

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
        if _curta_demais(fala):
            # "Certo.", "ok": pode ser ruído ou conversa ao lado. Confirma antes de mandar.
            return Decisao(f"{CONFIRMA_CENTRAL}“{fala.strip(' .!')}”? Diga sim pra eu mandar.")
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

        achados = roteiro.extrair_varios(e.ocorrencia_faltantes, fala)
        restantes = [c for c in e.ocorrencia_faltantes if c not in achados]
        prox = roteiro.proxima(e.ocorrencia_tipo, restantes)
        alerta = ""
        if roteiro.grave(e.ocorrencia_tipo, achados):
            alerta = ("Se ainda não ligaram, liga agora pro SAMU no 192 ou pros bombeiros no 193. "
                      "Já alertei o CCO como urgente. ")
        texto = alerta + (f"Anotado. {prox}" if prox else "Anotado, passei tudo pro CCO. Qualquer novidade, me fala.")
        return Decisao(texto, "detalhar_ocorrencia", achados)
    for tipo, padroes, rotulo in OCORRENCIAS:
        if _tem(t, *padroes):
            from . import ocorrencias as roteiro

            prox = roteiro.proxima(tipo, roteiro.campos_a_perguntar(tipo, fala)) or "Qualquer novidade, me fala."
            return Decisao(f"Registrei a ocorrência de {rotulo} e o CCO já tá vendo. {prox}",
                           "registrar_ocorrencia", {"tipo": tipo, "descricao": fala})
    if _tem(t, r"\boi\b", r"\bola\b", r"bom dia", r"boa tarde", r"boa noite", r"\be ai\b", r"tudo bem"):
        situacao = (f"Você tá parado há {e.tempo_parado} em {e.destino}." if e.tempo_parado
                    else f"Tô acompanhando a sua entrega em {e.destino}.")
        return Decisao(f"E aí, {e.nome}! {situacao} Qualquer coisa, me fala.")
    if pergunta:
        return Decisao(_status(e))
    return Decisao(_nao_entendi(e))


SIM = (r"^\s*(sim|isso|pode|confirm\w*|manda|ok|beleza|certo|positivo|exato|fechado)\b",)
NAO = (r"^\s*(nao|negativo|errado|espera|calma)\b",)
CONFIRMA_CENTRAL = "Respondo pra central: "
PERGUNTA_RECADO = "O que eu mando pro CCO?"


def _curta_demais(fala: str) -> bool:
    palavras = re.findall(r"\w+", fala or "")
    return len(palavras) <= 2 and not re.search(r"\d", fala or "")


def _central_a_confirmar(ultima_fala_agente: Optional[str]) -> Optional[str]:
    """Se o agente acabou de pedir confirmação da resposta à central, devolve o texto a mandar."""
    m = re.search(re.escape(CONFIRMA_CENTRAL) + r"“(.+?)”\?", ultima_fala_agente or "")
    return m.group(1) if m else None


def _pendencia_falada(e: "Estado") -> Optional[str]:
    from . import ocorrencias as roteiro

    if e.pergunta_central:
        return f"A central perguntou: {e.pergunta_central}"
    if e.retirada_pendente:
        return "Confirma a retirada da carga?"
    if e.chegada_pendente:
        return "Você chegou? Confirma a chegada?"
    if e.ocorrencia_tipo and e.ocorrencia_faltantes:
        return roteiro.proxima(e.ocorrencia_tipo, e.ocorrencia_faltantes)
    for faltantes in (e.checkin_faltantes, e.inicial_faltantes):
        if faltantes:
            return "Me conta: " + " e ".join(ROTULOS[k] for k in faltantes) + "?"
    return None


def _nao_entendi(e: "Estado") -> str:
    """Não entendeu: volta para o que está pendente; sem pendência, pede para repetir (sem listar tudo)."""
    pend = _pendencia_falada(e)
    if pend:
        return f"Não peguei. {pend}"
    if (e.ultima_fala_agente or "").startswith(("Não peguei", "Ainda não entendi")):
        return "Ainda não entendi. Fala com outras palavras?"
    return "Não peguei. Pode repetir de outro jeito? Por exemplo: cheguei, tem fila, ou quanto tempo tô parado."


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
