#!/usr/bin/env python3
"""Avalia o agente do motorista em conversas difíceis, contra a api e o LLM de verdade.

Cada cenário reinicia a rota, abre uma sessão de teste (sem Agora: só o endpoint que a Agora
chama, /v1/chat/completions, com o histórico acumulado como a Agora manda) e mostra, turno a
turno, o que o agente respondeu e o que ele registrou no sistema (eventos e ações no app).
Algumas checagens automáticas marcam OK/FALHOU; o resto é para ler.

Uso (dentro do Docker):  make avaliar           (ou ARGS="--cenario ruido" para um só)
Só biblioteca padrão + o pacote da api (para criar a sessão de teste).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")

from sqlmodel import select  # noqa: E402

from app.dominio import prompts  # noqa: E402
from app.infra.db import sessao  # noqa: E402
from app.infra.models import Evento, SessaoAgente, agora  # noqa: E402
from app.servicos import consultas  # noqa: E402

API = os.getenv("AVALIAR_API", "http://localhost:8000")
SEGREDO = os.getenv("LLM_SHARED_SECRET", "")
IGNORAR = {"fala_motorista", "fala_agente", "alerta_motorista", "evento_app"}

# (fala do motorista, checagem opcional sobre (resposta, eventos novos))
CENARIOS: dict[str, dict] = {
    "inicio": {
        "descricao": "Começo de viagem com respostas soltas",
        "turnos": [
            ("bom dia", None),
            ("peguei a carga já, bora", ("registra a retirada", lambda r, ev: "retirada" in ev)),
            ("o caminhão tá de boa", None),
            ("são os paletes de bebida", ("relatório completo, sem inventar", lambda r, ev: "relatorio" in ev)),
        ],
    },
    "ruido": {
        "descricao": "Conversa ao lado e ruído não podem virar registro",
        "turnos": [
            ("ô Zé, passa o café aí", ("não registra nada", lambda r, ev: not ev)),
            ("hahaha não, isso aí não", ("não registra nada", lambda r, ev: not ev)),
            ("quanto tempo eu tô parado?", ("não registra nada", lambda r, ev: not ev)),
        ],
    },
    "ocorrencia": {
        "descricao": "Ocorrência com desvio no meio",
        "turnos": [
            ("furou o pneu aqui", ("abre ocorrência", lambda r, ev: "ocorrencia" in ev)),
            ("abre o mapa aí rapidinho", ("não confunde com a ocorrência", lambda r, ev: "ocorrencia" not in ev)),
            ("a carga tá inteira, consigo seguir sim", ("detalha a ocorrência", lambda r, ev: "ocorrencia_detalhada" in ev)),
        ],
    },
    "central": {
        "descricao": "Resposta curta à central pede confirmação",
        "antes": [("POST", "/rotas/{rota}/solicitacoes", {"pergunta": "A carga está lacrada?"})],
        "turnos": [
            ("certo", ("não manda sem confirmar", lambda r, ev: "resposta_central" not in ev)),
            ("sim, tá lacrada", ("manda a resposta", lambda r, ev: "resposta_central" in ev)),
        ],
    },
    "vago": {
        "descricao": "Pedidos vagos pedem esclarecimento",
        "turnos": [
            ("manda pro CCO", ("não manda recado vazio", lambda r, ev: "chamado_cco_aberto" not in ev)),
            ("o que você faz?", None),
            ("repete", None),
        ],
    },
}


def req(metodo: str, caminho: str, corpo=None, headers=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    r = urllib.request.Request(API + caminho, data=dados, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt and txt[:1] in "{[" else txt)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def abrir_sessao(rota: int) -> int:
    with sessao() as s:
        sa = SessaoAgente(rota_id=rota, papel="motorista", canal="avaliacao", agent_uid=9001, user_uid=1001,
                          status="encerrada", llm_mode="custom", criada_em=agora(),
                          erro="avaliação de conversa (scripts/avaliar_conversas.py)")
        s.add(sa)
        s.commit()
        s.refresh(sa)
        return sa.id


def fechar_sessao(sid: int) -> None:
    with sessao() as s:
        sa = s.get(SessaoAgente, sid)
        if sa:
            s.delete(sa)
            s.commit()


def ultimo_evento_id(rota: int) -> int:
    with sessao() as s:
        ev = s.exec(select(Evento).where(Evento.rota_id == rota).order_by(Evento.id.desc())).first()
        return ev.id if ev else 0


def eventos_desde(rota: int, desde: int) -> list[str]:
    with sessao() as s:
        evs = s.exec(select(Evento).where(Evento.rota_id == rota, Evento.id > desde).order_by(Evento.id)).all()
    return [e.tipo for e in evs if e.tipo not in IGNORAR]


def rodar(nome: str, cenario: dict, rota: int) -> tuple[int, int]:
    req("POST", f"/rotas/{rota}/reset")
    r, motorista, empresa = consultas.contexto_rota(rota)
    sistema, saudacao = prompts.motorista(r, motorista, empresa)
    for metodo, caminho, corpo in cenario.get("antes", []):
        req(metodo, caminho.format(rota=rota), corpo)
    sid = abrir_sessao(rota)
    historico = [{"role": "system", "content": sistema}, {"role": "assistant", "content": saudacao}]
    headers = {"Authorization": f"Bearer {SEGREDO}"} if SEGREDO else {}
    ok = falhas = 0
    print(f"\n### {nome}: {cenario['descricao']}\n")
    try:
        for fala, checagem in cenario["turnos"]:
            desde = ultimo_evento_id(rota)
            historico.append({"role": "user", "content": fala})
            status, corpo = req("POST", f"/v1/chat/completions?sessao={sid}",
                                {"stream": False, "messages": historico}, headers)
            resposta = corpo["choices"][0]["message"]["content"] if status == 200 else f"[HTTP {status}] {corpo}"
            historico.append({"role": "assistant", "content": resposta})
            novos = eventos_desde(rota, desde)
            print(f"- **Motorista:** {fala}\n  **AvisAI:** {resposta}\n  registrou: {', '.join(novos) or '—'}")
            if checagem:
                rotulo, teste = checagem
                passou = bool(teste(resposta, novos))
                ok, falhas = ok + passou, falhas + (not passou)
                print(f"  {'OK' if passou else 'FALHOU'}: {rotulo}")
    finally:
        fechar_sessao(sid)
        req("POST", f"/rotas/{rota}/reset")
    return ok, falhas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rota", type=int, default=1)
    ap.add_argument("--cenario", choices=sorted(CENARIOS))
    args = ap.parse_args()
    escolhidos = {args.cenario: CENARIOS[args.cenario]} if args.cenario else CENARIOS
    _, saude = req("GET", "/health")
    modo = ("LLM configurado (se a chave for recusada, quem responde é a contingência; veja `make logs`)"
            if isinstance(saude, dict) and saude.get("llm_upstream") else "contingência (sem LLM)")
    print(f"# Avaliação de conversas · rota {args.rota} · {modo}")
    total_ok = total_falhas = 0
    for nome, cenario in escolhidos.items():
        ok, falhas = rodar(nome, cenario, args.rota)
        total_ok, total_falhas = total_ok + ok, total_falhas + falhas
    print(f"\n**Checagens:** {total_ok} ok, {total_falhas} falharam.")
    return 1 if total_falhas else 0


if __name__ == "__main__":
    sys.exit(main())
