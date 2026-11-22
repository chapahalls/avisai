"""Peça 6: Task do CCO, até N tentativas e, sem resposta, ligação ao recebedor."""
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import LigacaoRecebedor, RegraEscalonamento, TaskCCO
from app.servicos import sessoes, tasks
from tests.helpers import esperar, eventos, obter


def _ligacoes():
    with sessao() as s:
        return s.exec(select(LigacaoRecebedor)).all()


async def test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor(container, rota_id, fake_agora):
    await sessoes.iniciar_motorista(container, rota_id)
    t = await tasks.on_chegada(container, rota_id, origem="gps")
    await esperar(lambda: obter(TaskCCO, t.id).status == "escalada_recebedor")
    notifs = eventos("notificacao_cco")
    assert [n.dados["canal"] for n in notifs] == ["push", "painel", "ligacao"]
    assert [n.dados["prioridade"] for n in notifs] == ["normal", "alta", "critica"]
    assert all("valor_fmt" in n.dados["estadia"] for n in notifs)
    assert any("ligando pro recebimento" in f for f in fake_agora.falas())
    await esperar(lambda: len(_ligacoes()) == 1)
    assert _ligacoes()[0].task_id == t.id


async def test_cco_confirma_e_loop_para_sem_ligacao(container, rota_id, fake_agora):
    container.settings.cco_intervalo_s = 0.2
    await sessoes.iniciar_motorista(container, rota_id)
    t = await tasks.on_chegada(container, rota_id, origem="gps")
    await esperar(lambda: len(eventos("notificacao_cco")) == 1)
    await tasks.confirmar(container, t.id, "Ana (CCO)")
    t2 = obter(TaskCCO, t.id)
    assert t2.status == "confirmada" and t2.confirmado_por == "Ana (CCO)" and t2.confirmado_em
    import asyncio

    await asyncio.sleep(0.5)
    assert len(eventos("notificacao_cco")) == 1
    assert _ligacoes() == []
    assert any("CCO assumiu" in f for f in fake_agora.falas())


async def test_regra_da_empresa_define_numero_de_tentativas(container, rota_id):
    with sessao() as s:
        r = s.exec(select(RegraEscalonamento)).one()
        r.max_tentativas = 2
        s.add(r)
        s.commit()
    t = await tasks.on_chegada(container, rota_id, origem="gps")
    await esperar(lambda: obter(TaskCCO, t.id).status == "escalada_recebedor")
    assert len(eventos("notificacao_cco")) == 2
