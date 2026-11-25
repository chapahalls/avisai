#!/usr/bin/env python3
"""GPS simulado: move o caminhão pelo trajeto da rota, chamando POST /rotas/{id}/posicao.
Manda o GPS do celular e o do "rastreador do caminhão" (dupla prova; --divergir força a divergência).

Uso:
  python scripts/simular_rota.py                      # rota 1, http://localhost:8000
  python scripts/simular_rota.py --rota 1 --passo 1.5 --velocidade 60
  python scripts/simular_rota.py --desde 30           # começa no ponto 30 (perto da aproximação)

Só usa a biblioteca padrão. As geocercas (aproximação e chegada) são calculadas no backend.
"""
import argparse
import json
import time
import urllib.request


TOKEN = ""


def req(metodo: str, url: str, corpo: dict | None = None) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(url, data=dados, method=metodo, headers=h)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--rota", type=int, default=1)
    ap.add_argument("--passo", type=float, default=1.5, help="segundos entre posições")
    ap.add_argument("--velocidade", type=float, default=60, help="km/h informada ao backend (para o ETA)")
    ap.add_argument("--desde", type=int, default=0, help="índice inicial do trajeto")
    ap.add_argument("--reset", action="store_true", help="reseta a rota antes de começar")
    ap.add_argument("--sem-rastreador", action="store_true", help="manda só o GPS do celular")
    ap.add_argument("--divergir", action="store_true", help="rastreador ~1 km longe na chegada (testa a divergência)")
    a = ap.parse_args()

    # Com AUTH_OBRIGATORIA=true, mandar GPS exige token: o simulador entra como central (acessa qualquer rota).
    global TOKEN
    perfis = req("GET", f"{a.api}/usuarios?role=cco")
    if perfis:
        TOKEN = req("POST", f"{a.api}/auth/sso", {"email": perfis[0]["email"]}).get("token", "")

    if a.reset:
        req("POST", f"{a.api}/rotas/{a.rota}/reset")
    rota = req("GET", f"{a.api}/rotas/{a.rota}")
    pontos = rota["trajeto"]
    print(f"Rota {a.rota}: {rota['origem_nome']} -> {rota['destino_nome']} ({len(pontos)} pontos)")
    for i, (lat, lng) in enumerate(pontos[a.desde:], start=a.desde):
        if not a.sem_rastreador:  # "rastreador do caminhão": mesma posição com ruído de ~10 m
            dlat = 0.009 if a.divergir and i >= len(pontos) - 3 else 0.00008
            req("POST", f"{a.api}/rotas/{a.rota}/posicao", {"lat": lat + dlat, "lng": lng, "fonte": "rastreador"})
        r = req("POST", f"{a.api}/rotas/{a.rota}/posicao", {"lat": lat, "lng": lng, "velocidade_kmh": a.velocidade, "precisao_m": 8})
        extra = f"  >>> {', '.join(r['disparos'])}" if r.get("disparos") else ""
        print(f"[{i:02d}] {r['distancia_m'] / 1000:6.1f} km  ETA {r['eta_min']:5.1f} min  {r['status']}{extra}")
        if r["status"] == "no_destino" and i == len(pontos) - 1:
            break
        time.sleep(a.passo)
    print("Chegou. Acompanhe a Task e a estadia em /cco/stream.")


if __name__ == "__main__":
    main()
