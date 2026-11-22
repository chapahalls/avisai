"""População idempotente da demonstração, preservando dados e escolhas existentes.

Uso: python -m app.seed [--reset]
Sem --reset, complementa perfis e rotas identificadas por e-mail/NF; nunca reabre viagens.
Todos os nomes, placas e endereços dos dados de demonstração são fictícios.
"""
import sys
from collections import defaultdict

from sqlalchemy import func, text
from sqlmodel import select

from .infra import container as ct
from .infra.db import engine, sessao
from .infra.models import Empresa, Motorista, RegraEscalonamento, Rota, Usuario
from .servicos.usuarios import garantir_cco, garantir_motorista, normalizar_email

ORIGEM = ("CD Jundiaí", -23.1857, -46.8978)
DESTINO = ("Mercadão Campinas, CD Norte", -22.9056, -47.0608)
PERFIS_CCO = (
    ("cco@avisai.test", "Ana (CCO)"),
    ("cco.turno2@avisai.test", "Bruno (CCO)"),
)
MOTORISTAS_DEMO = (
    ("carlos@rotasul.test", "Carlos Andrade", "+5511900000001"),
    ("marina@rotasul.test", "Marina Souza", None),
    ("joao@rotasul.test", "João Pereira", None),
    ("fernanda@rotasul.test", "Fernanda Lima", None),
)
ROTAS_DEMO = (
    {
        "email": "marina@rotasul.test", "nota_fiscal": "DEMO-AVISAI-002", "placa": "DMO-2A02",
        "destino": ("Recebedor fictício DEMO · Sorocaba", -23.5015, -47.4526),
        "carga_descricao": "Carga fictícia DEMO: 18 paletes de limpeza", "carga_t": 18,
    },
    {
        "email": "joao@rotasul.test", "nota_fiscal": "DEMO-AVISAI-003", "placa": "DMO-3A03",
        "destino": ("Recebedor fictício DEMO · Sumaré", -22.8211, -47.2670),
        "carga_descricao": "Carga fictícia DEMO: 22 paletes de embalagens", "carga_t": 22,
    },
)


def trajeto(n: int = 40, origem=None, destino=None) -> list[list[float]]:
    """Trajeto simulado em linha reta (o GPS da demo é simulado; ver README)."""
    (la1, lo1), (la2, lo2) = origem or ORIGEM[1:], destino or DESTINO[1:]
    return [[round(la1 + (la2 - la1) * i / n, 6), round(lo1 + (lo2 - lo1) * i / n, 6)] for i in range(n + 1)]


def limpar() -> None:
    """Atalho destrutivo existente; usado apenas com --reset explícito."""
    with engine.begin() as c:
        tabelas = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"))]
        if tabelas:
            c.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tabelas) + " RESTART IDENTITY CASCADE"))


def seed(reset: bool = False) -> int:
    if reset:
        limpar()
    container = ct.atual()
    cfg = container.settings
    with sessao() as s:
        existing_route = s.exec(select(Rota).order_by(Rota.id)).first()
        emp = s.exec(select(Empresa).where(Empresa.nome == "Transportadora Rota Sul").order_by(Empresa.id)).first()
        if emp is None:
            emp = Empresa(nome="Transportadora Rota Sul")
            s.add(emp)
            s.flush()
        if s.exec(select(RegraEscalonamento).where(RegraEscalonamento.empresa_id == emp.id)).first() is None:
            s.add(RegraEscalonamento(empresa_id=emp.id, max_tentativas=3, intervalo_s=cfg.cco_intervalo_s,
                                     niveis=["push", "painel", "ligacao"], acao_final="ligar_recebedor"))

        drivers = {}
        for email, name, phone in MOTORISTAS_DEMO:
            matches = s.exec(select(Motorista).where(func.lower(func.trim(Motorista.email)) == email)
                             .order_by(Motorista.id)).all()
            if len(matches) > 1:
                # Não apaga duplicatas legadas nem escolhe uma identidade ambígua.
                continue
            driver = matches[0] if matches else None
            if driver is None and email == "carlos@rotasul.test":
                # Backfill restrito ao fixture histórico que originalmente não tinha e-mail.
                legacy = s.exec(
                    select(Motorista).join(Rota, Rota.motorista_id == Motorista.id)
                    .where(
                        Motorista.empresa_id == emp.id,
                        Motorista.nome == "Carlos Andrade",
                        Motorista.telefone_e164 == "+5511900000001",
                        (Motorista.email.is_(None) | (func.trim(Motorista.email) == "")),
                        Rota.empresa_id == emp.id,
                        Rota.placa == "RST-4B21",
                        Rota.nota_fiscal == "000.482.913",
                    )
                ).all()
                legacy = {candidate.id: candidate for candidate in legacy}
                if len(legacy) == 1:
                    driver = next(iter(legacy.values()))
                    driver.email = email
            if driver is None:
                driver = Motorista(empresa_id=emp.id, nome=name, telefone_e164=phone, email=email)
            s.add(driver)
            s.flush()
            drivers[email] = driver

        # Inclui também cadastros preexistentes com e-mail único, sem renomeá-los.
        by_email = defaultdict(list)
        for driver in s.exec(select(Motorista).order_by(Motorista.id)).all():
            if driver.email:
                try:
                    by_email[normalizar_email(driver.email)].append(driver)
                except ValueError:
                    continue
        for matches in by_email.values():
            if len(matches) == 1:
                garantir_motorista(s, matches[0])
        for email, name in PERFIS_CCO:
            garantir_cco(s, email, name)

        if existing_route is None and "carlos@rotasul.test" in drivers:
            carlos = drivers["carlos@rotasul.test"]
            existing_route = Rota(
                empresa_id=emp.id, motorista_id=carlos.id,
                origem_nome=ORIGEM[0], origem_lat=ORIGEM[1], origem_lng=ORIGEM[2],
                destino_nome=DESTINO[0], destino_lat=DESTINO[1], destino_lng=DESTINO[2], trajeto=trajeto(),
                placa="RST-4B21", nota_fiscal="000.482.913", carga_descricao="28 paletes de bebidas", carga_t=28, capacidade_t=30,
                janela_descarga="hoje, 14h às 16h", recebedor_empresa="Mercadão Campinas",
                recebedor_nome="Marcos, do recebimento", recebedor_telefone_e164=cfg.recebedor_telefone_e164,
                aproximacao_min=15, raio_chegada_m=300, publicada_em=None,
            )
            s.add(existing_route)
            s.flush()

        for item in ROTAS_DEMO:
            if s.exec(select(Rota).where(Rota.nota_fiscal == item["nota_fiscal"])).first() is not None:
                continue
            driver = drivers.get(item["email"])
            if driver is None:
                continue
            # Uma pessoa já com histórico atribuído não recebe uma jornada nova no seed.
            # Inclui viagens concluídas: uma futura execução também preserva a escolha.
            if s.exec(select(Rota.id).where(Rota.motorista_id == driver.id)).first() is not None:
                continue
            name, lat, lng = item["destino"]
            s.add(Rota(
                empresa_id=emp.id, motorista_id=driver.id, status="planejada",
                origem_nome=ORIGEM[0], origem_lat=ORIGEM[1], origem_lng=ORIGEM[2],
                destino_nome=name, destino_lat=lat, destino_lng=lng,
                trajeto=trajeto(origem=ORIGEM[1:], destino=(lat, lng)), placa=item["placa"],
                nota_fiscal=item["nota_fiscal"], carga_descricao=item["carga_descricao"], carga_t=item["carga_t"],
                janela_descarga="Demonstração · horário a combinar", recebedor_empresa=name,
                recebedor_nome="Contato fictício DEMO", recebedor_telefone_e164="",
                publicada_em=container.relogio.agora(), atribuida_em=container.relogio.agora(),
            ))
        s.commit()
        if existing_route is None:
            existing_route = s.exec(select(Rota).order_by(Rota.id)).first()
        if existing_route is None:
            raise ValueError("Cadastros de demonstração ambíguos; nenhuma rota inicial disponível")
        return existing_route.id


def resumo() -> dict:
    with sessao() as s:
        profiles = s.exec(select(Usuario)).all()
        return {
            "usuarios": len(profiles), "cco": sum(user.papel == "cco" for user in profiles),
            "perfis_motoristas": sum(user.papel == "driver" for user in profiles),
            "motoristas": len(s.exec(select(Motorista)).all()), "rotas": len(s.exec(select(Rota)).all()),
        }


if __name__ == "__main__":
    rid = seed(reset="--reset" in sys.argv)
    print(f"seed ok: rota_id={rid}; " + ", ".join(f"{key}={value}" for key, value in resumo().items()))
