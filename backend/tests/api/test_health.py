"""`/health` precisa refletir o banco de verdade, não só dizer "ok" com o processo de pé no ar
(risco encontrado no deploy da Vercel: DATABASE_URL não configurada, mas /health respondia ok=true).

Também expõe o `sha` da imagem e devolve 503 (não 200) quando `ok` é falso: o alerta do júri era que
`curl -fsS` no fim do deploy (ci.yml) não detectava banco fora do ar, porque /health sempre respondia 200."""
from app.infra import db
from app.infra import container as ct


async def test_health_ok_com_banco_de_pe(client):
    r = await client.get("/health")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ok"] is True
    assert corpo["banco_ok"] is True


async def test_health_ok_falso_quando_o_banco_nao_responde(client, monkeypatch):
    # porta sem ninguém escutando (não uma resolução de DNS, que pode demorar ou cair em outro host)
    monkeypatch.setattr(db, "engine", db.create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x"))
    r = await client.get("/health")
    assert r.status_code == 503  # não 200: um curl -fsS/load balancer precisa detectar isso como falha
    corpo = r.json()
    assert corpo["ok"] is False
    assert corpo["banco_ok"] is False


async def test_health_expoe_o_sha_do_build(client):
    ct.atual().settings.git_sha = "abc1234"
    r = await client.get("/health")
    assert r.json()["sha"] == "abc1234"
