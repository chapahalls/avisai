"""Comandos do app por voz: a fala vira uma intenção fechada; o app nunca recebe a transcrição."""
import pytest

from app.dominio.comandos_app import Comando, interpretar, payload_cliente, validar


@pytest.mark.parametrize("fala,esperado", [
    ("Abre o mapa", Comando("abrir_tela", tela="mapa")),
    ("me mostra a rota", Comando("abrir_tela", tela="mapa")),
    ("Vai pras mensagens", Comando("abrir_tela", tela="mensagens")),
    ("Mudar para documentos", Comando("abrir_tela", tela="documentos")),
    ("troca pro mapa", Comando("abrir_tela", tela="mapa")),
    ("abrir a fila do recebedor", Comando("abrir_tela", tela="fila")),
    ("mostra os documentos da viagem", Comando("abrir_tela", tela="documentos")),
    ("volta pro início", Comando("abrir_tela", tela="inicio")),
    ("Abre a nota fiscal", Comando("abrir_documento", documento="NF-e")),
    ("mostra o CT-e", Comando("abrir_documento", documento="CT-e")),
    ("volta", Comando("voltar")),
    ("Pode encerrar a conversa", Comando("encerrar_conversa")),
    ("tchau, AvisAI", Comando("encerrar_conversa")),
    ("quero sair da conta", Comando("sair_da_conta")),
    ("Confirmo, sair da conta", Comando("sair_da_conta", confirmado=True)),
])
def test_fala_vira_comando(fala, esperado):
    assert interpretar(fala) == esperado


@pytest.mark.parametrize("fala", [
    "me mostra o peso da nota",       # pergunta sobre o documento: consultar_documento
    "qual o valor do frete no CT-e?",
    "a fila tá enorme aqui",          # ocorrência, não navegação
    "falta a nota fiscal",
    "cheguei na portaria",
    "",
])
def test_fala_que_nao_e_comando(fala):
    assert interpretar(fala) is None


def test_validar_recusa_tela_e_acao_desconhecidas():
    assert validar({"acao": "abrir_tela", "tela": "cozinha"})[0] is None
    assert validar({"acao": "formatar_celular"})[0] is None
    assert validar({"acao": "abrir_documento"})[0] is None


def test_payload_so_leva_a_intencao():
    cmd, _ = validar({"acao": "abrir_documento", "documento": "nota fiscal"})
    assert payload_cliente(1, cmd) == {"rota_id": 1, "acao": "open_document", "documento": "NF-e"}
    cmd, _ = validar({"acao": "encerrar_conversa"})
    assert payload_cliente(1, cmd) == {"rota_id": 1, "acao": "end_voice"}
