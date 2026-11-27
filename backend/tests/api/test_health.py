"""`/health` precisa refletir o banco de verdade, não só dizer "ok" com o processo de pé no ar
(risco encontrado no deploy da Vercel: DATABASE_URL não configurada, mas /health respondia ok=true)."""
from app.infra import db


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
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ok"] is False
    assert corpo["banco_ok"] is False
