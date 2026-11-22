"""Peça 7: o agente liga para o recebedor (plano B por RTC, plano A por SIP com fallback)."""
from app.infra.models import LigacaoRecebedor, SessaoAgente, TaskCCO
from app.integracoes.agora_rest import AgoraErro
from app.servicos import ligacoes, sessoes
from tests.helpers import eventos, esperar, obter


async def _task(container, rota_id):
    from app.infra.db import sessao

    with sessao() as s:
        t = TaskCCO(rota_id=rota_id, status="escalada_recebedor", tentativas=3)
        s.add(t)
        s.commit()
        s.refresh(t)
    return t


async def test_plano_b_agente_entra_no_canal_do_recebedor(container, rota_id, fake_agora):
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert lig.modo == "rtc"
    assert lig.status == "em_andamento"
    assert lig.canal == f"avisai-recebedor-{lig.id}"
    p = fake_agora.ultimo_join()["properties"]
    assert p["channel"] == lig.canal
    assert p["agent_rtc_uid"] == "9002"
    assert p["remote_rtc_uids"] == ["3001"]
    prompt = p["llm"]["system_messages"][0]["content"]
    assert "assistente virtual" in prompt and "RST-4B21" in prompt and "000.482.913" in prompt
    assert "?sessao=" in p["llm"]["url"]
    ev = eventos("ligacao_recebedor")[-1]
    assert ev.dados["pagina_recebedor"].endswith(f"/recebedor?ligacao={lig.id}")


async def test_sem_resposta_ate_o_timeout_vira_nao_atendida_e_prova(container, rota_id, fake_agora):
    await sessoes.iniciar_motorista(container, rota_id)
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    await esperar(lambda: obter(LigacaoRecebedor, lig.id).status == "nao_atendida")
    assert eventos("ligacao_nao_atendida")
    assert any("não atendeu" in f for f in fake_agora.falas())
    await esperar(lambda: "agent-2" in fake_agora.leaves)


async def test_falha_no_join_registra_ligacao_falhou(container, rota_id, fake_agora):
    fake_agora.falhar_join = AgoraErro(500, "boom")
    try:
        await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    except AgoraErro:
        pass
    from app.infra.db import sessao
    from sqlmodel import select

    with sessao() as s:
        lig = s.exec(select(LigacaoRecebedor)).one()
    assert lig.status == "falhou" and "500" in lig.erro
    assert eventos("ligacao_falhou")


async def test_plano_a_liga_por_sip_para_o_numero_do_recebedor(container, rota_id, fake_agora):
    container.settings.recebedor_modo = "sip"
    container.settings.agora_sip_from_number = "+5511999990000"
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert lig.modo == "sip"
    sip = fake_agora.calls[-1]["sip"]
    assert sip["to_number"] == "+5519900000002"
    assert sip["from_number"] == "+5511999990000"
    assert sip["rtc_uid"] == "3001" and sip["rtc_token"].startswith("007")
    await esperar(lambda: obter(LigacaoRecebedor, lig.id).atendida)


async def test_plano_a_desligou_sem_resposta_vira_nao_atendida(container, rota_id, fake_agora):
    container.settings.recebedor_modo = "sip"
    container.settings.agora_sip_from_number = "+5511999990000"
    fake_agora.estado_call = {"state": "hangup"}
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    await esperar(lambda: obter(LigacaoRecebedor, lig.id).status == "nao_atendida")


async def test_plano_a_falhando_cai_no_plano_b(container, rota_id, fake_agora):
    container.settings.recebedor_modo = "sip"
    container.settings.agora_sip_from_number = "+5511999990000"
    fake_agora.falhar_call = AgoraErro(400, "invalid_phone_format")
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert lig.modo == "rtc" and lig.status == "em_andamento"
    assert fake_agora.joins, "deveria ter entrado pelo canal RTC"
    assert "invalid_phone_format" in eventos("fallback_plano_b")[-1].mensagem


async def test_plano_a_sem_numero_configurado_cai_no_plano_b(container, rota_id, fake_agora):
    container.settings.recebedor_modo = "sip"
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta")
    assert lig.modo == "rtc"
    assert eventos("fallback_plano_b")


async def test_resposta_do_recebedor_vai_para_task_e_motorista(container, rota_id, fake_agora):
    await sessoes.iniciar_motorista(container, rota_id)
    t = await _task(container, rota_id)
    lig = await ligacoes.ligar(container, rota_id, motivo="cco_sem_resposta", task_id=t.id)
    sa_id = obter(LigacaoRecebedor, lig.id).sessao_id
    await ligacoes.registrar_resposta(container, sa_id, previsao="em 40 minutos", doca="4", motivo=None,
                                      resumo="A doca 4 libera em 40 minutos.")
    lig = obter(LigacaoRecebedor, lig.id)
    assert lig.status == "respondida" and lig.atendida and lig.doca == "4"
    assert obter(TaskCCO, t.id).resposta_recebedor == "A doca 4 libera em 40 minutos."
    fala = fake_agora.speaks[-1]
    assert fala["prioridade"] == "INTERRUPT" and fala["agent_id"] == "agent-1"
    assert "doca 4" in fala["texto"] and "40 minutos" in fala["texto"]
    assert eventos("resposta_recebedor")
    await esperar(lambda: obter(SessaoAgente, sa_id).status == "encerrada")
