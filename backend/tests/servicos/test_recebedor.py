"""Chamadas ao recebedor em RTC e por SIP LiveKit."""
from app.integracoes.livekit import LiveKitErro
from app.infra.models import LigacaoRecebedor, SessaoAgente, TaskCCO
from app.servicos import ligacoes, sessoes
from tests.helpers import eventos, esperar, obter


async def _task(container, rota_id):
    from app.infra.db import sessao

    with sessao() as db:
        task = TaskCCO(rota_id=rota_id, status="escalada_recebedor", tentativas=3)
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


async def test_plano_rtc_despacha_agente_na_sala_do_recebedor(container, rota_id, fake_livekit):
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert call.modo == "rtc" and call.status == "em_andamento"
    assert call.canal == f"rodar-recebedor-{call.id}"
    dispatch = fake_livekit.dispatches[-1]
    assert dispatch["room"] == call.canal
    assert dispatch["metadata"]["role"] == "recebedor"
    assert "assistente virtual" in dispatch["metadata"]["instructions"]
    assert "RST-4B21" in dispatch["metadata"]["instructions"]
    assert eventos("ligacao_recebedor")[-1].dados["pagina_recebedor"].endswith(f"/recebedor?ligacao={call.id}")


async def test_sem_resposta_ate_timeout_registra_tentativa(container, rota_id, fake_livekit):
    await sessoes.iniciar_motorista(container, rota_id)
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    await esperar(lambda: obter(LigacaoRecebedor, call.id).status == "nao_atendida")
    assert eventos("ligacao_nao_atendida")
    assert any("não atendeu" in text for text in fake_livekit.falas())
    await esperar(lambda: (call.canal, f"rodar-agente-{call.sessao_id}") in fake_livekit.removals)


async def test_falha_no_dispatch_registra_ligacao_falhou(container, rota_id, fake_livekit):
    fake_livekit.falhar_dispatch = LiveKitErro(500, "boom")
    try:
        await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    except LiveKitErro:
        pass
    from app.infra.db import sessao
    from sqlmodel import select

    with sessao() as db:
        call = db.exec(select(LigacaoRecebedor)).one()
    assert call.status == "falhou" and "500" in call.erro
    assert eventos("ligacao_falhou")


async def test_sip_livekit_cria_participante_para_numero_do_recebedor(container, rota_id, fake_livekit):
    container.settings.recebedor_modo = "sip"
    container.settings.livekit_sip_trunk_id = "trunk-test"
    container.settings.livekit_sip_from_number = "+5511999990000"
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert call.modo == "sip"
    assert fake_livekit.dial_requests[-1] == {
        "room": call.canal, "number": "+5519900000002", "identity": f"sip-recebedor-{call.id}"
    }
    await esperar(lambda: obter(LigacaoRecebedor, call.id).atendida)


async def test_sip_hangup_sem_resposta_marca_nao_atendida(container, rota_id, fake_livekit):
    container.settings.recebedor_modo = "sip"
    container.settings.livekit_sip_trunk_id = "trunk-test"
    fake_livekit.sip_status = "hangup"
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    await esperar(lambda: obter(LigacaoRecebedor, call.id).status == "nao_atendida")


async def test_falha_ao_criar_sip_faz_fallback_para_rtc(container, rota_id, fake_livekit):
    container.settings.recebedor_modo = "sip"
    container.settings.livekit_sip_trunk_id = "trunk-test"
    fake_livekit.falhar_dial = LiveKitErro(400, "invalid_phone_format")
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert call.modo == "rtc" and call.status == "em_andamento"
    assert fake_livekit.dispatches[-1]["metadata"]["role"] == "recebedor"
    assert "invalid_phone_format" in eventos("fallback_plano_b")[-1].mensagem


async def test_sip_sem_trunk_configurado_faz_fallback_para_rtc(container, rota_id):
    container.settings.recebedor_modo = "sip"
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert call.modo == "rtc"
    assert eventos("fallback_plano_b")


async def test_resposta_do_recebedor_vai_para_task_e_motorista(container, rota_id, fake_livekit):
    await sessoes.iniciar_motorista(container, rota_id)
    task = await _task(container, rota_id)
    call = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta", task_id=task.id)
    session_id = obter(LigacaoRecebedor, call.id).sessao_id
    await ligacoes.registrar_resposta(container, session_id, previsao="em 40 minutos", doca="4", motivo=None,
                                      resumo="A doca 4 libera em 40 minutos.")
    call = obter(LigacaoRecebedor, call.id)
    assert call.status == "respondida" and call.atendida and call.doca == "4"
    assert obter(TaskCCO, task.id).resposta_recebedor == "A doca 4 libera em 40 minutos."
    speech = fake_livekit.speaks[-1]
    assert speech["prioridade"] == "INTERRUPT" and speech["agent_id"] == "dispatch-1"
    assert "doca 4" in speech["texto"] and "40 minutos" in speech["texto"]
    assert eventos("resposta_recebedor")
    await esperar(lambda: obter(SessaoAgente, session_id).status == "encerrada")
