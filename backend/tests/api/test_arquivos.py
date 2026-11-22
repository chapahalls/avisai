"""Anexos reais: persistência, contrato mobile e fronteiras de upload/download."""
import asyncio
from pathlib import Path

import pytest
from sqlmodel import select

from app.api import cco
from app.infra.db import sessao
from app.infra.models import ArquivoRota
from tests.api.test_publicacao_rota import NOVA

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"fixture"
JPEG = b"\xff\xd8\xff\xe0" + b"fixture"
WEBP = b"RIFF\x10\x00\x00\x00WEBP" + b"fixture"
GIF = b"GIF89a" + b"fixture"


@pytest.fixture(autouse=True)
def isolated_files(container, tmp_path):
    container.settings.arquivos_dir = str(tmp_path / "uploads")
    return tmp_path / "uploads"


async def upload(client, content=PDF, filename="nota.pdf", mime="application/pdf", data=None, rota_id=1):
    return await client.post(f"/rotas/{rota_id}/arquivos",
                             files={"arquivo": (filename, content, mime)}, data=data or {})


async def test_upload_lista_download_e_evento(client, container, isolated_files, fake_agora):
    assert (await client.get("/rotas/1/arquivos")).json() == []
    response = await upload(client, data={"categoria": "nota_fiscal", "descricao": "  NF anexada  "})
    assert response.status_code == 201, response.text
    item = response.json()
    assert set(item) == {"id", "rota_id", "nome_original", "tipo_mime", "tamanho_bytes",
                         "categoria", "descricao", "criado_em", "url_download"}
    assert item["rota_id"] == 1 and item["id"] > 0
    assert item["nome_original"] == "nota.pdf" and item["tipo_mime"] == "application/pdf"
    assert item["tamanho_bytes"] == len(PDF) and item["descricao"] == "NF anexada"
    assert item["categoria"] == "nota_fiscal" and item["criado_em"].endswith("Z")
    assert item["url_download"] == f"/rotas/1/arquivos/{item['id']}/download"
    assert (await client.get("/rotas/1/arquivos")).json() == [item]
    download = await client.get(item["url_download"])
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "private, no-store"
    assert len(list(isolated_files.iterdir())) == 1
    event = next(e for e in (await client.get("/eventos")).json() if e["tipo"] == "arquivo_adicionado")
    assert event["rota_id"] == 1 and event["dados"]["arquivo_id"] == item["id"]
    domain = (await client.get("/events", params={"tripId": "1"})).json()
    assert any(e["type"] == "TripFileAdded" and e["source"] == "cco" for e in domain)
    assert fake_agora.joins == [] and fake_agora.speaks == [] and fake_agora.calls == []


@pytest.mark.parametrize("filename,content,mime", [
    ("imagem.png", PNG, "image/png"), ("foto.JPEG", JPEG, "image/jpeg"),
    ("imagem.webp", WEBP, "image/webp"), ("imagem.gif", GIF, "image/gif"),
    ("nota.pdf", PDF, "application/octet-stream"),
])
async def test_formatos_permitidos(client, filename, content, mime):
    response = await upload(client, content, filename, mime)
    assert response.status_code == 201, response.text
    item = response.json()
    assert (await client.get(item["url_download"])).content == content


@pytest.mark.parametrize("filename", ["../../segredo.pdf", "..\\..\\segredo.pdf", "/tmp/segredo.pdf"])
async def test_nome_nao_controla_caminho(client, isolated_files, filename):
    response = await upload(client, filename=filename)
    assert response.status_code == 201
    item = response.json()
    assert item["nome_original"] == "segredo.pdf"
    files = list(isolated_files.iterdir())
    assert len(files) == 1 and files[0].name != "segredo.pdf"
    assert files[0].parent == isolated_files
    assert (await client.get(item["url_download"])).content == PDF


async def test_mesmo_nome_cria_ids_e_conteudos_distintos(client):
    first = (await upload(client)).json()
    content = PDF + b"outra versao"
    second = (await upload(client, content)).json()
    assert first["id"] != second["id"]
    assert (await client.get(first["url_download"])).content == PDF
    assert (await client.get(second["url_download"])).content == content


@pytest.mark.parametrize("filename,content,mime", [
    ("script.svg", b"<svg/>", "image/svg+xml"),
    ("arquivo.pdf", b"<script>alert(1)</script>", "application/pdf"),
    ("foto.png", JPEG, "image/png"),
    ("nota.pdf", PDF, "text/html"),
    ("arquivo.pdf", b"", "application/pdf"),
])
async def test_rejeita_formato_ou_assinatura_incorreta(client, isolated_files, filename, content, mime):
    response = await upload(client, content, filename, mime)
    assert response.status_code == 415
    assert (await client.get("/rotas/1/arquivos")).json() == []
    assert not isolated_files.exists() or list(isolated_files.iterdir()) == []


async def test_limite_exato_e_arquivo_maior_sem_parcial(client, container, isolated_files):
    container.settings.arquivos_max_bytes = len(PDF)
    assert (await upload(client)).status_code == 201
    assert (await upload(client, PDF + b"x")).status_code == 413
    assert len((await client.get("/rotas/1/arquivos")).json()) == 1
    assert len(list(isolated_files.iterdir())) == 1
    assert not list(isolated_files.glob("*.part"))


async def test_corpo_grande_e_chunked_limitados_antes_do_parser(client, container, isolated_files):
    container.settings.arquivos_max_bytes = 16
    assert (await upload(client, PDF + b"x" * 100_000)).status_code == 413
    boundary = "fixture"
    header = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"nota.pdf\"\r\n"
              "Content-Type: application/pdf\r\n\r\n").encode()

    async def body():
        yield header
        yield PDF
        yield b"x" * 100_000
        yield f"\r\n--{boundary}--\r\n".encode()

    response = await client.post("/rotas/1/arquivos", content=body(),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert response.status_code == 413
    assert not isolated_files.exists() or list(isolated_files.iterdir()) == []
    assert (await client.get("/rotas/1/arquivos")).json() == []


async def test_rota_arquivo_ou_conteudo_ausentes_404(client, container):
    assert (await client.get("/rotas/999/arquivos")).status_code == 404
    assert (await upload(client, rota_id=999)).status_code == 404
    assert (await client.get("/rotas/1/arquivos/999/download")).status_code == 404
    item = (await upload(client)).json()
    other = (await client.post("/rotas", json=NOVA)).json()
    assert (await client.get(f"/rotas/{other['id']}/arquivos/{item['id']}/download")).status_code == 404
    with sessao() as s:
        stored = s.get(ArquivoRota, item["id"])
    (Path(container.settings.arquivos_dir) / stored.chave_storage).unlink()
    assert (await client.get(item["url_download"])).status_code == 404


async def test_chave_adulterada_e_symlink_nao_saem_da_raiz(client, container, isolated_files, tmp_path):
    item = (await upload(client)).json()
    with sessao() as s:
        stored = s.get(ArquivoRota, item["id"])
        original = stored.chave_storage
        stored.chave_storage = "../../segredo.pdf"
        s.add(stored)
        s.commit()
    assert (await client.get(item["url_download"])).status_code == 404
    with sessao() as s:
        stored = s.get(ArquivoRota, item["id"])
        stored.chave_storage = original
        s.add(stored)
        s.commit()
    destination = tmp_path / "segredo"
    destination.write_bytes(b"segredo")
    path = isolated_files / original
    path.unlink()
    path.symlink_to(destination)
    assert (await client.get(item["url_download"])).status_code == 404


async def test_reset_operacional_preserva_anexos(client):
    item = (await upload(client)).json()
    assert (await client.post("/rotas/1/reset")).status_code == 200
    assert (await client.get("/rotas/1/arquivos")).json() == [item]
    assert (await client.get(item["url_download"])).content == PDF


async def test_categoria_e_descricao_invalida(client):
    assert (await upload(client, data={"categoria": "qualquer"})).status_code == 422
    assert (await upload(client, data={"descricao": "x" * 1001})).status_code == 422
    assert (await client.get("/rotas/1/arquivos")).json() == []


async def test_ws_motorista_recebe_evento_do_arquivo(client, container):
    gen = cco.fluxo(container, motorista_id=1, intervalo_contador=60)
    await gen.__anext__()
    item = (await upload(client)).json()
    channel, event = await asyncio.wait_for(gen.__anext__(), 2)
    assert channel == "evento" and event["tipo"] == "arquivo_adicionado"
    assert event["dados"]["arquivo_id"] == item["id"]
    await gen.aclose()
