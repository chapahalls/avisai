"""Offline-first: fala gravada sem sinal chega depois, é transcrita e vira registro do agente."""
import struct
from pathlib import Path

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Ocorrencia
from tests.fakes import tool_call
from tests.helpers import esperar, eventos


def wav(segundos: float = 0.5) -> bytes:
    dados = b"\x00\x00" * int(16000 * segundos)
    cab = b"RIFF" + struct.pack("<I", 36 + len(dados)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    return cab + fmt + b"data" + struct.pack("<I", len(dados)) + dados


async def enviar(client, chave: str = "k-1", audio: bytes | None = None, falado_em: str = "2026-11-22T13:50:00Z"):
    return await client.post(
        "/rotas/1/falas-offline",
        files={"audio": ("fala.wav", audio if audio is not None else wav(), "audio/wav")},
        data={"idempotencyKey": chave, "faladoEm": falado_em, "duracaoMs": "500"},
    )


def fala_offline():
    evs = eventos("fala_offline")
    return evs[0] if evs else None


async def test_fala_offline_vira_ocorrencia_e_aviso(client, container, fake_llm, fake_transcritor):
    fake_transcritor.texto = "Furou o pneu no km 230 da BR-381"
    fake_llm.respostas = [
        tool_call("registrar_ocorrencia", '{"tipo":"avaria","descricao":"pneu furado","km":230,"rodovia":"BR-381"}'),
        "Registrei a ocorrência de pneu furado no km 230.",
    ]
    r = await enviar(client)
    assert r.status_code == 201 and r.json()["status"] == "accepted"

    ev = await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "processada" and e)
    assert ev.source == "driver" and ev.mensagem == "Mensagem de voz gravada sem sinal às 10h50"
    assert ev.dados["transcricao"] == "Furou o pneu no km 230 da BR-381"
    # Transcrito com sucesso: o áudio é apagado, só a transcrição fica registrada.
    assert not (Path(container.settings.falas_offline_dir) / ev.dados["arquivo"]).exists()
    with sessao() as s:
        o = s.exec(select(Ocorrencia)).one()
    assert o.tipo == "avaria" and o.km == 230
    # O agente soube que a fala é antiga e que o motorista não está ouvindo.
    sistema = [m["content"] for m in fake_llm.recebidas[0]["mensagens"] if m["role"] == "system"]
    assert any("FALA GRAVADA SEM SINAL" in t and "às 10h50" in t and "há 10 minutos" in t for t in sistema)
    avisos = [e.mensagem for e in eventos("fala_agente")]
    assert "Sobre o que você falou às 10h50: Registrei a ocorrência de pneu furado no km 230." in avisos
    assert [e.mensagem for e in eventos("fala_motorista")] == ["Furou o pneu no km 230 da BR-381"]


async def test_mesma_fala_duas_vezes_devolve_409_e_nao_duplica(client, container, fake_transcritor):
    assert (await enviar(client)).status_code == 201
    r = await enviar(client)
    assert r.status_code == 409 and r.json()["status"] == "duplicate"
    await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "processada" and e)
    assert len(eventos("fala_offline")) == 1 and len(fake_transcritor.recebidos) == 1
    # Transcrito com sucesso, o único áudio gravado é apagado: a chave repetida não deixou um
    # segundo arquivo (que, não tendo evento associado, nunca seria processado nem removido).
    assert not list(Path(container.settings.falas_offline_dir).iterdir())


async def test_formato_desconhecido_e_recusado(client):
    r = await enviar(client, audio=b"isto nao e audio" * 10)
    assert r.status_code == 415 and not eventos("fala_offline")


async def test_audio_grande_demais_e_recusado(client, container):
    container.settings.falas_offline_max_bytes = 1000
    r = await enviar(client, audio=wav(1))
    assert r.status_code == 413 and not eventos("fala_offline")


async def test_sem_transcritor_guarda_o_audio_sem_texto(client, container):
    container.transcritor = None
    assert (await enviar(client)).status_code == 201
    ev = await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "sem_transcricao" and e)
    assert (Path(container.settings.falas_offline_dir) / ev.dados["arquivo"]).exists()


async def test_falha_na_transcricao_fica_registrada(client, container, fake_transcritor, fake_llm):
    fake_transcritor.falhar = True
    await enviar(client)
    ev = await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "erro_transcricao" and e)
    assert "STT fora do ar" in ev.dados["erro"] and not fake_llm.recebidas
    # Falhou a transcrição: o áudio é mantido em disco para diagnóstico.
    assert (Path(container.settings.falas_offline_dir) / ev.dados["arquivo"]).exists()


async def test_horario_no_futuro_vira_horario_de_chegada(client):
    await enviar(client, falado_em="2030-01-01T00:00:00Z")
    ev = await esperar(fala_offline)
    assert ev.mensagem == "Mensagem de voz gravada sem sinal às 11h00"


async def test_falas_da_mesma_rota_sao_processadas_em_ordem(client, fake_transcritor, fake_llm):
    fake_llm.respostas = ["Anotei a primeira.", "Anotei a segunda."]
    await enviar(client, chave="k-1")
    await enviar(client, chave="k-2", falado_em="2026-11-22T13:55:00Z")
    await esperar(lambda: all(e.dados.get("status") == "processada" for e in eventos("fala_offline"))
                  and len(eventos("fala_offline")) == 2)
    avisos = [e.mensagem for e in eventos("fala_agente")]
    assert avisos == ["Sobre o que você falou às 10h50: Anotei a primeira.",
                      "Sobre o que você falou às 10h55: Anotei a segunda."]


async def test_fala_offline_nao_confirma_retirada_que_nao_foi_dita(client, fake_llm, fake_transcritor):
    fake_transcritor.texto = "Furou o pneu no km 230. A carga tá inteira."
    fake_llm.respostas = [tool_call("confirmar_retirada", "{}"), "Anotei o pneu."]
    await enviar(client)
    await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "processada")
    assert not eventos("retirada")


async def test_fala_offline_confirma_retirada_quando_dita(client, fake_llm, fake_transcritor):
    fake_transcritor.texto = "Peguei a carga, bora pra estrada."
    fake_llm.respostas = [tool_call("confirmar_retirada", "{}"), "Retirada registrada."]
    await enviar(client)
    await esperar(lambda: (e := fala_offline()) and e.dados.get("status") == "processada")
    assert eventos("retirada")
