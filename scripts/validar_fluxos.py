#!/usr/bin/env python3
"""Validação ponta a ponta dos fluxos do repo de ideias, contra a api real (e a Agora real).

Percorre uma viagem inteira numa rota nova: publicação/atribuição, retirada, relatório inicial,
aproximação + ligação ao recebedor (doca e "não recebe hoje"), chegada com dupla prova de GPS,
check-in com campo faltante, ocorrência, pergunta sobre a NF, pedido da central, escalonamento do CCO
+ ligação, CCO assume, descarga, eventos do contrato (DomainEvent), métricas e divergência de GPS.

As falas do motorista e do recebedor são simuladas pelo mesmo endpoint que a Agora chama
(/v1/chat/completions); /join, /speak e /leave vão para a Agora de verdade.

Uso (dentro do Docker; grava o relatório em evidence/):  make validar
Só biblioteca padrão. Sai com código 1 se alguma etapa falhar.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

API = os.getenv("VALIDAR_API", "http://localhost:8000")
SEGREDO = os.getenv("LLM_SHARED_SECRET", "")
RESULTADOS: list[tuple[str, bool, str]] = []


_TOKEN_CCO: str | None = None


def _token_cco() -> str:
    """Faz login como CCO uma vez: com AUTH_OBRIGATORIA=true, as ações da central exigem esse token."""
    global _TOKEN_CCO
    if _TOKEN_CCO is None:
        _TOKEN_CCO = ""
        _, perfis = req("GET", "/usuarios?role=cco", autenticar=False)
        if isinstance(perfis, list) and perfis:
            _, sso = req("POST", "/auth/sso", {"email": perfis[0]["email"]}, autenticar=False)
            _TOKEN_CCO = sso.get("token", "") if isinstance(sso, dict) else ""
    return _TOKEN_CCO


def req(metodo: str, caminho: str, corpo=None, headers=None, autenticar=True):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    if autenticar and "Authorization" not in h and _token_cco():
        h["Authorization"] = f"Bearer {_token_cco()}"
    r = urllib.request.Request(API + caminho, data=dados, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt and not txt.startswith("data:") else txt)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def falar(sessao_id: int, fala: str) -> str:
    """Simula uma fala (como a Agora faria) e devolve o texto que o agente responderia."""
    h = {"Authorization": f"Bearer {SEGREDO}"} if SEGREDO else {}
    _, txt = req("POST", f"/v1/chat/completions?sessao={sessao_id}",
                 {"stream": True, "messages": [{"role": "user", "content": fala}]}, h)
    partes = []
    for linha in str(txt).splitlines():
        if linha.startswith("data: ") and linha[6:] != "[DONE]":
            partes.append(json.loads(linha[6:])["choices"][0]["delta"].get("content", ""))
    return "".join(partes).strip()


def eventos(rota_id: int) -> list[dict]:
    """Linha do tempo da rota em ordem cronológica (a api devolve do mais novo para o mais antigo)."""
    return sorted(req("GET", f"/eventos?rota_id={rota_id}&limite=500")[1], key=lambda e: e["id"])


def tipos(rota_id: int) -> set[str]:
    return {e["tipo"] for e in eventos(rota_id)}


def esperar(cond, timeout=30.0, passo=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(passo)
    return None


def etapa(nome: str, ok: bool, detalhe: str = "") -> bool:
    RESULTADOS.append((nome, bool(ok), detalhe))
    print(f"{'✅' if ok else '❌'} {nome}" + (f" — {detalhe}" if detalhe else ""), file=sys.stderr, flush=True)
    return ok


def posicao(rota_id: int, lat: float, lng: float, rastreador: tuple | None = None, vel: float = 60) -> dict:
    if rastreador:
        req("POST", f"/rotas/{rota_id}/posicao", {"lat": rastreador[0], "lng": rastreador[1], "fonte": "rastreador"})
    return req("POST", f"/rotas/{rota_id}/posicao", {"lat": lat, "lng": lng, "velocidade_kmh": vel, "precisao_m": 8})[1]


def ligacao(rota_id: int, motivo: str, desde: int = 0):
    ligs = [l for l in req("GET", "/ligacoes")[1] if l["rota_id"] == rota_id and l["motivo"] == motivo and l["id"] > desde]
    return ligs[0] if ligs else None


NOVA_ROTA = {
    "origem": {"nome": "CD Jundiaí", "lat": -23.1857, "lng": -46.8978},
    "destino": {"nome": "Atacado Valinhos", "lat": -22.9706, "lng": -46.9958},
    "recebedor": {"empresa": "Atacado Valinhos", "nome": "Rita, do recebimento", "telefone_e164": "+5519900000004"},
    "carga_descricao": "20 paletes de bebidas", "carga_t": 20, "capacidade_t": 24, "placa": "VAL-1D23",
    "nota_fiscal": "000.600.111", "janela_descarga": "hoje, 15h às 17h",
}


def main() -> int:
    inicio = datetime.now(BRT)
    _, saude = req("GET", "/health")
    print(f"api: {API} · llm_upstream={saude.get('llm_upstream')} · recebedor={saude.get('recebedor_modo')}", file=sys.stderr)

    # 1. Publicação e atribuição
    _, mot = req("POST", "/motoristas", {"nome": "Validador Automático", "email": f"validador-{int(time.time())}@rotasul.test"})
    st, rota = req("POST", "/rotas", {**NOVA_ROTA, "motorista_id": mot["id"]})
    R = rota["id"] if st == 200 else None
    if not etapa("1. CCO publica a rota e atribui ao motorista", st == 200 and rota.get("status") == "planejada",
                 f"rota {R}, motorista {mot['id']}"):
        return relatorio(inicio, saude)
    _, sso = req("POST", "/auth/sso", {"email": mot["email"]})
    etapa("1b. Login do motorista traz a rota atribuída (SSO mock)", sso["user"]["tripId"] == str(R))

    # 2. Sessão do agente (Agora real)
    st, s = req("POST", "/sessions", {"rota_id": R})
    S = s.get("id") if st == 200 else None
    etapa("2. Agente ConvoAI entra no canal do motorista (/join na Agora)", st == 200 and s.get("agent_id"),
          f"agent_id {s.get('agent_id', s)}" if st == 200 else str(s)[:200])
    if not S:
        return relatorio(inicio, saude)

    # 3. Retirada na origem + relatório inicial
    trajeto = req("GET", f"/rotas/{R}")[1]["trajeto"]
    r = posicao(R, *trajeto[0], rastreador=(trajeto[0][0] + 0.00008, trajeto[0][1]))
    etapa("3. Geocerca da origem dispara a pergunta da retirada", "RETIRADA" in r["disparos"]
          and any("Confirma a retirada" in e["mensagem"] for e in eventos(R)))
    resp = falar(S, "Confirmo, peguei a carga")
    etapa("3b. Retirada confirmada por voz", "retirada" in tipos(R), f"agente: {resp}")
    resp = falar(S, "Caminhão tá tudo certo, peguei 20 paletes")
    etapa("3c. Relatório inicial completo por voz", any(e["tipo"] == "relatorio" and e["dados"].get("tipo_reporte") == "inicial"
                                                        for e in eventos(R)), f"agente: {resp}")

    # 3d. Atraso na estrada → recebedor avisado do novo horário
    for p in trajeto[1:6]:
        posicao(R, *p, rastreador=(p[0] + 0.00008, p[1]))
    resp = falar(S, "Vou atrasar uns 40 minutos, trânsito parado")
    lig_at = esperar(lambda: (l := ligacao(R, "atraso")) and l["status"] == "em_andamento" and l, 30)
    aviso_at = esperar(lambda: any(e["tipo"] == "aviso_recebedor" and e["dados"].get("motivo") == "atraso" for e in eventos(R)), 10)
    etapa("3d. Atraso na estrada: agente liga para o recebedor com o novo horário", bool(lig_at and aviso_at), f"agente: {resp}")
    if lig_at:
        falar(lig_at["sessao_id"], "Tudo bem, a doca 3 às 16h")

    # 4. Viagem até a aproximação → aviso e ligação ao recebedor
    for p in trajeto[6:]:
        r = posicao(R, *p, rastreador=(p[0] + 0.00008, p[1]))
        if "APROXIMACAO" in r["disparos"]:
            break
    etapa("4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado", "aproximacao" in tipos(R), f"ETA {r['eta_min']} min")
    lig = esperar(lambda: (l := ligacao(R, "aproximacao")) and l["status"] == "em_andamento" and l, 30)
    avisado = esperar(lambda: "aviso_recebedor" in tipos(R), 10)
    etapa("4b. Agente liga para o recebedor na aproximação (ReceiverNotified)",
          bool(lig and avisado), f"ligação {lig and lig['id']} via {lig and lig['modo']}")
    if lig:
        resp = falar(lig["sessao_id"], "A doca 4 libera em 40 minutos")
        l2 = req("GET", f"/ligacoes/{lig['id']}")[1]
        etapa("4c. Resposta do recebedor registrada (doca e previsão)", l2["status"] == "respondida" and l2["doca"] == "4",
              f"previsão '{l2['previsao']}', agente: {resp}")
        etapa("4d. Motorista ouve a resposta do recebedor (/speak)",
              any(e["tipo"] == "fala_agente" and "doca 4" in e["mensagem"] for e in eventos(R)))
        ultimo = lig["id"]
        req("POST", f"/rotas/{R}/ligar-recebedor", {"motivo": "aproximacao"})
        lig2 = esperar(lambda: (l := ligacao(R, "aproximacao", desde=ultimo)) and l["status"] == "em_andamento" and l, 30)
        if lig2:
            falar(lig2["sessao_id"], "Hoje não recebemos mais, só amanhã")
        etapa("4e. Recebedor 'não recebe hoje' aplica a regra da transportadora",
              "nao_recebe_hoje" in tipos(R), "evento nao_recebe_hoje" if "nao_recebe_hoje" in tipos(R) else "sem evento")

    # 5. Chegada com dupla prova
    dest = trajeto[-1]
    r = posicao(R, *dest, rastreador=(dest[0] + 0.00008, dest[1]), vel=5)
    geo_ok = any(e["tipo"] == "chegada" for e in eventos(R))
    etapa("5. Chegada (GPS + rastreador) cria Task e inicia a estadia", "CHEGADA" in r["disparos"] and geo_ok
          and any(t["rota_id"] == R for t in req("GET", "/tasks")[1]))
    etapa("5b. Sem divergência de GPS quando celular e rastreador concordam", "divergencia_gps" not in tipos(R))
    etapa("5x. Agente pede a confirmação da chegada (GPS detectou)",
          any(e["tipo"] == "fala_agente" and "Confirma a chegada" in e["mensagem"] for e in eventos(R)))
    resp = falar(S, "Sim, confirmo")
    etapa("5y. Chegada confirmada por voz (prova GPS + rastreador + voz)", "chegada_confirmada_voz" in tipos(R), f"agente: {resp}")
    est0 = req("GET", f"/cco/estado?rota_id={R}")[1]["estadias"]
    etapa("5z. Estadia calculada sobre a capacidade do veículo (24 t, carga 20 t)", est0 and est0[0]["capacidade_t"] == 24)
    resp = falar(S, "A carga tá inteira")
    etapa("5c. Check-in parcial: agente pergunta só o que faltou", "campo_faltante" in tipos(R), f"agente: {resp}")
    resp = falar(S, "Foram três horas de viagem, sem problema")
    etapa("5d. Check-in completo", any(e["tipo"] == "relatorio" and e["dados"].get("tipo_reporte") == "checkin"
                                       for e in eventos(R)), f"agente: {resp}")
    resp = falar(S, "Tem uma fila de caminhões aqui na portaria")
    etapa("5e. Ocorrência por voz e o agente se aprofunda (pergunta de acompanhamento)",
          any(e["tipo"] == "ocorrencia" and e["dados"].get("tipo_ocorrencia") == "fila" for e in eventos(R))
          and "caminhões" in resp and "?" in resp, f"agente: {resp}")
    r1 = falar(S, "Uns cinco caminhões na frente")
    r2 = falar(S, "Disseram que em meia hora")
    etapa("5e2. Respostas do aprofundamento viram ocorrência detalhada para o CCO",
          any(e["tipo"] == "ocorrencia_detalhada" and e["dados"].get("tipo_ocorrencia") == "fila"
              and e["dados"]["detalhes"].get("quantos") for e in eventos(R)), f"agente: {r1} / {r2}")
    resp = falar(S, "Qual o peso da nota?")
    etapa("5f. Pergunta sobre a NF responde com o documento", "20.000 kg" in resp and "NF-e" in resp, f"agente: {resp}")
    resp = falar(S, "Quanto tempo eu tô parado?")
    etapa("5g. Pergunta de tempo parado usa o estado real", "parado" in resp.lower(), f"agente: {resp}")

    # 6. Pedido da central
    req("POST", f"/rotas/{R}/solicitacoes", {"pergunta": "Qual o número do lacre?"})
    resp = falar(S, "O lacre é 4471")
    sols = req("GET", f"/rotas/{R}/solicitacoes")[1]
    etapa("6. Pedido da central: pergunta ao motorista e resposta estruturada",
          sols and sols[0]["status"] == "respondida" and "4471" in (sols[0]["resposta"] or ""), f"agente: {resp}")

    # 7. Escalonamento do CCO → ligação ao recebedor
    task = esperar(lambda: next((t for t in req("GET", "/tasks")[1] if t["rota_id"] == R
                                 and t["status"] == "escalada_recebedor"), None), 150, 3)
    notifs = [e for e in eventos(R) if e["tipo"] == "notificacao_cco"]
    etapa("7. CCO sem resposta: 3 tentativas (push → painel → ligação)",
          [n["dados"]["canal"] for n in notifs][:3] == ["push", "painel", "ligacao"], f"{len(notifs)} notificações")
    lig3 = esperar(lambda: (l := ligacao(R, "cco_sem_resposta")) and l["status"] == "em_andamento" and l, 30)
    etapa("7b. Após 3 tentativas o agente liga para o recebedor", task is not None and lig3 is not None)
    if lig3:
        falar(lig3["sessao_id"], "A doca 2 libera às 15h")
        t2 = next(t for t in req("GET", "/tasks")[1] if t["rota_id"] == R)
        etapa("7c. Resposta do recebedor vai para a Task", bool(t2.get("resposta_recebedor")), t2.get("resposta_recebedor") or "")
    if task:
        st, t3 = req("POST", f"/tasks/{task['id']}/confirmar", {"confirmado_por": "Validador (CCO)"})
        etapa("7d. CCO assume a Task e o motorista é avisado", st == 200 and t3["status"] == "confirmada"
              and any("CCO assumiu" in e["mensagem"] for e in eventos(R)))

    # 8. Descarga
    resp = falar(S, "Descarreguei")
    est = [e for e in req("GET", f"/cco/estado?rota_id={R}")[1]["estadias"]]
    etapa("8. Descarga por voz encerra a estadia e a Task", "descarga" in tipos(R) and est and est[0]["encerrada"],
          f"agente: {resp}")

    # 9. Contrato dos fronts (DomainEvent) e métricas
    dominios = {e["type"] for e in req("GET", f"/events?tripId={R}")[1]}
    esperados = {"RouteAssigned", "PickupConfirmed", "ReportSubmitted", "ReportFieldMissing", "OccurrenceCreated",
                 "ApproachDetected", "ReceiverNotified", "ReceiverCallResult", "ArrivalRegistered", "TaskCreated",
                 "TaskEscalated", "TaskAcknowledged", "UnloadConfirmed", "DocumentQuestionAnswered"}
    faltam = esperados - dominios
    etapa("9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7)", not faltam,
          "faltam: " + ", ".join(sorted(faltam)) if faltam else "todos presentes")
    _, m = req("GET", "/api/metrics")
    etapa("9b. KPIs calculados (/api/metrics)", m.get("entregas", 0) >= 1, f"entregas {m.get('entregas')}, "
          f"estadia devida {m.get('estadia_devida_total')}, % avisados {m.get('pct_recebedores_avisados')}")
    rec = req("GET", "/api/receivers")[1]
    etapa("9c. Ranking de recebedores inclui o recebedor da viagem", any(x["recebedor"] == "Atacado Valinhos" for x in rec))

    # 10. Divergência de GPS (rota curta separada)
    _, r3 = req("POST", "/rotas", {**NOVA_ROTA, "placa": "DIV-0000", "motorista_id": mot["id"]})
    R3 = r3["id"]
    posicao(R3, NOVA_ROTA["destino"]["lat"], NOVA_ROTA["destino"]["lng"], rastreador=(NOVA_ROTA["destino"]["lat"] + 0.01, NOVA_ROTA["destino"]["lng"]), vel=5)
    etapa("10. Celular × rastreador divergentes: evento não validado e alerta ao CCO", "divergencia_gps" in tipos(R3))
    t_div = next((t for t in req("GET", "/tasks")[1] if t["rota_id"] == R3), None)
    if t_div:  # encerra para não escalar
        req("POST", f"/tasks/{t_div['id']}/confirmar", {"confirmado_por": "Validador"})
        req("POST", f"/rotas/{R3}/descarga", {"por": "Validador"})

    req("DELETE", f"/sessions/{S}")
    return relatorio(inicio, saude)


def relatorio(inicio: datetime, saude: dict) -> int:
    ok = sum(1 for _, v, _ in RESULTADOS if v)
    print(f"# Validação ponta a ponta — {inicio:%Y-%m-%d %H:%M} (BRT)\n")
    print(f"Api `{API}` · LLM upstream: {'sim' if saude.get('llm_upstream') else 'não (contingência)'} · "
          f"recebedor: {saude.get('recebedor_modo')} · duração {int((datetime.now(BRT) - inicio).total_seconds())} s\n")
    print(f"**{ok}/{len(RESULTADOS)} etapas OK**\n")
    print("| Etapa | Resultado | Detalhe |\n|---|---|---|")
    for nome, v, d in RESULTADOS:
        print(f"| {nome} | {'✅' if v else '❌'} | {d.replace('|', '/')[:220]} |")
    print("\nFalas simuladas pelo mesmo endpoint que a Agora chama; /join, /speak e /leave reais na Agora. "
          "Não substitui o teste com pessoas falando (qualidade do ASR, latência, barge-in).")
    return 0 if ok == len(RESULTADOS) else 1


if __name__ == "__main__":
    sys.exit(main())
