"""O LLM não pode gravar no relatório o que o motorista não disse."""
from app.dominio.fundamentacao import fundamentado, so_o_que_ele_disse


def test_dados_da_rota_que_ele_nao_disse_sao_recusados():
    aceitos, recusados = so_o_que_ele_disse(
        {"estado_caminhao": "pronto para viagem", "carga": "28 paletes de bebidas"}, "peguei a carga já, bora")
    assert aceitos == {} and set(recusados) == {"estado_caminhao", "carga"}


def test_o_que_ele_disse_passa_mesmo_reescrito():
    assert fundamentado("estado_caminhao", "em boas condições", "o caminhão tá de boa")
    assert fundamentado("carga", "paletes de bebida", "são os paletes de bebida")
    assert fundamentado("problemas", "nenhum", "foi sem problema nenhum")
    assert fundamentado("tempo_viagem", "3 horas", "deu umas três horas")


def test_sem_fala_para_comparar_aceita():
    assert fundamentado("carga", "qualquer coisa", None)
