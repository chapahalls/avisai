"""Diálogo sem LLM: entende a intenção e responde com o estado da rota (domínio puro)."""
import pytest

from app.dominio import contingencia as ct
from app.dominio.contingencia import Estado

VAZIO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito")
PARADO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                tempo_parado="1 hora e 20 minutos", franquia_restante="3 horas e 40 minutos",
                valor="R$ 0,00", task_status="pendente", tentativas_cco=2)
RESPONDIDO = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                    tempo_parado="6 horas", franquia_restante="0 minutos", valor="R$ 70,00",
                    task_status="escalada_recebedor", doca="4", previsao="em 40 minutos",
                    resumo_recebedor="A doca 4 libera em 40 minutos.")


@pytest.mark.parametrize("fala", ["Cheguei na portaria", "tô no pátio do cliente", "chegamos aqui no Mercadão", "estou na portaria"])
def test_chegada(fala):
    d = ct.decidir("motorista", fala, VAZIO)
    assert d.ferramenta == "confirmar_chegada"


@pytest.mark.parametrize("fala", ["Descarreguei", "já terminou a descarga", "liberaram o caminhão, tá vazio"])
def test_descarga(fala):
    assert ct.decidir("motorista", fala, PARADO).ferramenta == "confirmar_descarga"


@pytest.mark.parametrize("fala,tipo", [
    ("tem uma fila de três caminhões", "fila"),
    ("a doca tá ocupada", "doca_ocupada"),
    ("pediram outra nota fiscal", "documento"),
    ("furou um pneu", "avaria"),
    ("o recebedor recusou a carga", "recusa"),
    ("vou atrasar uns trinta minutos", "atraso"),
])
def test_ocorrencias(fala, tipo):
    d = ct.decidir("motorista", fala, PARADO)
    assert d.ferramenta == "registrar_ocorrencia" and d.args["tipo"] == tipo and d.args["descricao"] == fala


def test_pergunta_tempo_parado_responde_com_estado():
    d = ct.decidir("motorista", "quanto tempo eu tô parado?", PARADO)
    assert d.ferramenta is None
    assert "1 hora e 20 minutos" in d.texto and "3 horas e 40 minutos" in d.texto


def test_pergunta_estadia_valor():
    d = ct.decidir("motorista", "quanto já deu de estadia?", RESPONDIDO)
    assert "R$ 70,00" in d.texto


def test_pergunta_doca_com_resposta_do_recebedor():
    d = ct.decidir("motorista", "e aí, qual a doca?", RESPONDIDO)
    assert d.ferramenta is None and "doca 4" in d.texto and "40 minutos" in d.texto


def test_pergunta_doca_sem_resposta_ainda():
    d = ct.decidir("motorista", "alguma notícia da doca?", PARADO)
    assert d.ferramenta is None and "CCO" in d.texto


def test_pergunta_sobre_cco():
    d = ct.decidir("motorista", "o CCO respondeu?", PARADO)
    assert "2" in d.texto or "duas" in d.texto


def test_saudacao_resume_situacao():
    d = ct.decidir("motorista", "bom dia", PARADO)
    assert d.ferramenta is None and "Carlos" in d.texto and "parado" in d.texto


def test_nao_entendeu_pede_para_repetir_com_exemplos():
    d = ct.decidir("motorista", "o senhor é o editor que investigamos", VAZIO)
    assert d.ferramenta is None
    # Pede para repetir com exemplos curtos, em vez de listar tudo o que o agente faz.
    assert "repetir" in d.texto and "cheguei" in d.texto and "fila" in d.texto


def test_acentos_e_maiusculas_nao_atrapalham():
    assert ct.decidir("motorista", "CHEGUEI NA PORTARIA", VAZIO).ferramenta == "confirmar_chegada"
    assert ct.decidir("motorista", "descarreguei já", PARADO).ferramenta == "confirmar_descarga"


@pytest.mark.parametrize("fala,doca,prev", [
    ("a doca 4 libera em 40 minutos", "4", "em 40 minutos"),
    ("pode mandar pra doca dois às 15h", "2", "às 15h"),
    ("daqui uma hora na doca 7", "7", "daqui uma hora"),
])
def test_recebedor_extrai_doca_e_previsao(fala, doca, prev):
    d = ct.decidir("recebedor", fala, PARADO)
    assert d.ferramenta == "registrar_resposta_recebedor"
    assert d.args["doca"] == doca and d.args["previsao"] == prev and d.args["resumo"] == fala


def test_recebedor_nao_recebe_hoje():
    d = ct.decidir("recebedor", "hoje não recebemos mais, só amanhã", PARADO)
    assert d.ferramenta == "registrar_resposta_recebedor" and "amanhã" in d.args["previsao"]


def test_recebedor_sem_resposta_agente_pergunta_de_novo():
    d = ct.decidir("recebedor", "alô? quem fala?", PARADO)
    assert d.ferramenta is None and "doca" in d.texto


# ---------- fluxos do repo de ideias ----------
NA_ORIGEM = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="na_origem", retirada_pendente=True)
INICIAL = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito",
                 inicial_faltantes=["estado_caminhao", "carga"])
CHECKIN = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="no_destino",
                 checkin_faltantes=["status_carga", "tempo_viagem", "problemas"])
CENTRAL = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="em_transito", pergunta_central="Qual o número do lacre?")


def test_confirma_retirada_na_origem():
    d = ct.decidir("motorista", "confirmo, peguei a carga", NA_ORIGEM)
    assert d.ferramenta == "confirmar_retirada" and "caminhão" in d.texto


def test_iniciar_viagem_confirma_retirada_sem_pedir_localizacao():
    planejada = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="planejada")
    d = ct.decidir("motorista", "quero iniciar a viagem", planejada)
    assert d.ferramenta == "confirmar_retirada"
    assert "km" not in d.texto.lower() and "br" not in d.texto.lower()


def test_relatorio_inicial_extrai_campos():
    d = ct.decidir("motorista", "caminhão tá tudo certo, peguei 28 paletes", INICIAL)
    assert d.ferramenta == "registrar_relatorio_inicial"
    assert d.args["estado_caminhao"] and d.args["carga"]


def test_checkin_parcial_pergunta_so_o_que_falta():
    d = ct.decidir("motorista", "a carga tá inteira", CHECKIN)
    assert d.ferramenta == "registrar_checkin" and d.args == {"status_carga": "ok"}
    assert "tempo de viagem" in d.texto and "problema" in d.texto and "carga" not in d.texto.split("E ")[-1]


def test_checkin_completo_numa_frase():
    d = ct.decidir("motorista", "carga ok, foram três horas de viagem, sem problema", CHECKIN)
    assert d.args == {"status_carga": "ok", "tempo_viagem": "três horas", "problemas": "nenhum"}
    assert "completo" in d.texto


def test_resposta_para_a_central():
    d = ct.decidir("motorista", "o lacre é 4471", CENTRAL)
    assert d.ferramenta == "responder_central" and d.args["resposta"] == "o lacre é 4471"


def test_chegada_ja_pede_o_checkin():
    d = ct.decidir("motorista", "cheguei", VAZIO)
    assert "tempo de viagem" in d.texto


def test_recebedor_nao_recebe_hoje_marca_recebe_hoje_false():
    d = ct.decidir("recebedor", "Hoje não recebemos mais, só amanhã", PARADO)
    assert d.args.get("recebe_hoje") is False


def test_recebedor_com_doca_nao_marca_recebe_hoje():
    assert "recebe_hoje" not in ct.decidir("recebedor", "a doca 4 libera em 40 minutos", PARADO).args


def test_problema_na_portaria_e_ocorrencia_nao_chegada():
    d = ct.decidir("motorista", "Tem uma fila de caminhões aqui na portaria", PARADO)
    assert d.ferramenta == "registrar_ocorrencia" and d.args["tipo"] == "fila"
    assert "caminhões" in d.texto  # já pergunta quantos na frente


# ---------- contexto da conversa: não se perder ----------
from dataclasses import replace as _replace  # noqa: E402


def test_resposta_curta_a_central_pede_confirmacao_e_o_sim_manda():
    d = ct.decidir("motorista", "Certo.", CENTRAL)
    assert d.ferramenta is None and "Respondo pra central" in d.texto and "Certo" in d.texto
    depois = _replace(CENTRAL, ultima_fala_agente=d.texto)
    d2 = ct.decidir("motorista", "sim", depois)
    assert d2.ferramenta == "responder_central" and d2.args["resposta"] == "Certo"
    d4 = ct.decidir("motorista", "sim, tá lacrada", depois)
    assert d4.args["resposta"] == "sim, tá lacrada"
    d3 = ct.decidir("motorista", "não", depois)
    assert d3.ferramenta is None and "Qual é a resposta" in d3.texto


def test_sem_entender_volta_para_a_pendencia():
    d = ct.decidir("motorista", "hmm sei lá", NA_ORIGEM)
    assert d.texto == "Não peguei. Confirma a retirada da carga?"
    d = ct.decidir("motorista", "hmm sei lá", CHECKIN)
    assert d.texto.startswith("Não peguei. Me conta:")


def test_sem_entender_e_sem_pendencia_nao_lista_tudo_nem_repete_igual():
    d = ct.decidir("motorista", "hmm sei lá", VAZIO)
    assert d.texto.startswith("Não peguei. Pode repetir")
    d2 = ct.decidir("motorista", "hmm", _replace(VAZIO, ultima_fala_agente=d.texto))
    assert d2.texto == "Ainda não entendi. Fala com outras palavras?"


PLANEJADA = Estado(nome="Carlos", destino="Mercadão Campinas", status_rota="planejada")


@pytest.mark.parametrize("fala", ["peguei a carga já, bora", "carreguei, partiu", "tô carregado"])
def test_falas_naturais_de_inicio_de_viagem(fala):
    d = ct.decidir("motorista", fala, PLANEJADA)
    assert d.ferramenta == "confirmar_retirada" and "como tá o caminhão" in d.texto


def test_bora_sozinho_em_viagem_nao_reinicia_nada():
    assert ct.decidir("motorista", "bora", VAZIO).ferramenta is None


def test_recado_sem_texto_pergunta_e_a_proxima_fala_vira_o_recado():
    d = ct.decidir("motorista", "manda pro CCO", VAZIO)
    assert d.ferramenta is None and d.texto == "O que eu mando pro CCO?"
    d2 = ct.decidir("motorista", "vou parar pra almoçar", _replace(VAZIO, ultima_fala_agente=d.texto))
    assert d2.ferramenta == "enviar_mensagem_cco" and d2.args == {"texto": "vou parar pra almoçar"}
    d3 = ct.decidir("motorista", "tem fila enorme aqui", _replace(VAZIO, ultima_fala_agente=d.texto))
    assert d3.ferramenta == "registrar_ocorrencia"  # problema continua ocorrência


def test_repete_repete_a_ultima_fala_e_o_que_eu_perdi_traz_avisos():
    e = _replace(VAZIO, ultima_fala_agente="Faltam uns 15 minutos.", ultimos_avisos=["a", "b", "O CCO respondeu: doca 2."])
    assert ct.decidir("motorista", "repete", e).texto == "Faltam uns 15 minutos."
    assert "doca 2" in ct.decidir("motorista", "o que eu perdi?", e).texto


def test_o_que_voce_faz():
    d = ct.decidir("motorista", "o que você faz?", VAZIO)
    assert d.ferramenta is None and "ocorrência" in d.texto


def test_uma_fala_responde_varias_perguntas_da_ocorrencia():
    e = _replace(VAZIO, ocorrencia_tipo="avaria", ocorrencia_faltantes=["o_que", "consegue_seguir", "carga"])
    d = ct.decidir("motorista", "furou o pneu, mas a carga tá inteira e consigo seguir", e)
    assert d.ferramenta == "detalhar_ocorrencia"
    assert set(d.args) == {"o_que", "consegue_seguir", "carga"} and d.args["consegue_seguir"] == "sim"


# ---------- borda das ferramentas: 4c (doca/previsão) e 5e2 (ocorrência detalhada) ----------

@pytest.mark.parametrize("valor,esperado", [
    ("doca 4", "4"),
    ("Doca: 4", "4"),
    ("DOCA 12", "12"),
    ("4", "4"),
    (None, None),
    ("doca", "doca"),  # só o prefixo, sem número: não há o que tirar
])
def test_normalizar_doca_tira_o_prefixo(valor, esperado):
    assert ct.normalizar_doca(valor) == esperado


def test_extrair_doca_previsao_da_transcricao():
    doca, previsao, nao_recebe = ct.extrair_doca_previsao("A doca 4 libera em 40 minutos")
    assert doca == "4" and previsao == "em 40 minutos" and nao_recebe is False


def test_extrair_doca_previsao_sem_nada_na_fala():
    assert ct.extrair_doca_previsao("oi, um minuto") == (None, None, False)


def test_extrair_doca_previsao_usa_a_ultima_doca_dita_quando_o_recebedor_se_corrige():
    """O recebedor às vezes se corrige na mesma fala; a doca que vale é a última, não a 1ª
    (re.findall(...)[-1] em vez de re.search, que pegaria "2")."""
    doca, _, _ = ct.extrair_doca_previsao("Ih, falei errado, não é a doca 2, é a doca 4 mesmo")
    assert doca == "4"


def test_resposta_livre_ocorrencia_aceita_resposta_da_pergunta_pendente():
    achados = ct.resposta_livre_ocorrencia("fila", ["quantos", "previsao"], "Uns cinco caminhões na frente")
    assert achados == {"quantos": "Uns cinco caminhões na frente"}


def test_resposta_livre_ocorrencia_ignora_pergunta_do_motorista():
    # "quanto tempo" é uma pergunta do motorista, não uma resposta à pergunta da ocorrência.
    assert ct.resposta_livre_ocorrencia("atraso", ["quanto", "motivo"], "Quanto tempo eu tô parado?") == {}


def test_resposta_livre_ocorrencia_ignora_outro_problema():
    # mudou de assunto: isso é um pneu furado, não a previsão da fila aberta.
    assert ct.resposta_livre_ocorrencia("fila", ["quantos", "previsao"], "Agora furou um pneu") == {}


def test_resposta_livre_ocorrencia_sem_ocorrencia_aberta():
    assert ct.resposta_livre_ocorrencia(None, None, "Uns cinco caminhões") == {}


@pytest.mark.parametrize("fala", ["ok", "beleza", "obrigado", "tô chegando"])
def test_resposta_livre_ocorrencia_descarta_confirmacao_generica(fala):
    """Sem número, hora/duração, sim/não explícito ou o padrão do próprio campo, uma confirmação
    genérica não responde nada da ocorrência — sem essa guarda, "beleza, obrigado" virava
    quantos="beleza, obrigado" (o LLM de verdade confirma o pedido sem responder à pergunta)."""
    assert ct.resposta_livre_ocorrencia("fila", ["quantos", "previsao"], fala) == {}


def test_resposta_livre_ocorrencia_aceita_sim_nao_explicito():
    assert ct.resposta_livre_ocorrencia("acidente", ["feridos"], "sim") == {"feridos": "sim"}


def test_resposta_livre_ocorrencia_aceita_hora_ou_duracao():
    achados = ct.resposta_livre_ocorrencia("doca_ocupada", ["previsao"], "Chega em uma hora")
    assert achados == {"previsao": "Chega em uma hora"}


def test_resposta_livre_ocorrencia_aceita_padrao_do_detecta_sem_numero():
    achados = ct.resposta_livre_ocorrencia("avaria", ["consegue_seguir"], "Dá pra seguir sim")
    assert achados == {"consegue_seguir": "sim"}
