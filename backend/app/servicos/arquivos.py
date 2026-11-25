"""Anexos reais da viagem: IDs no banco e conteúdo sob uma raiz local confiável."""
import re
import unicodedata
import uuid
from datetime import UTC
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlmodel import select

from ..dominio.enums import TipoEvento
from ..infra.db import sessao
from ..infra.eventos import envelope
from ..infra.models import ArquivoRota, Evento
from . import consultas

EXTENSIONS = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
STORAGE_EXTENSION = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
                     "image/webp": ".webp", "image/gif": ".gif"}
STORAGE_KEY = re.compile(r"[a-f0-9]{32}\.(pdf|jpg|png|webp|gif)")


def metadados(item: ArquivoRota) -> dict:
    return {
        "id": item.id, "rota_id": item.rota_id, "nome_original": item.nome_original,
        "tipo_mime": item.tipo_mime, "tamanho_bytes": item.tamanho_bytes, "categoria": item.categoria,
        "descricao": item.descricao, "criado_em": item.criado_em.replace(tzinfo=UTC),
        "url_download": f"/rotas/{item.rota_id}/arquivos/{item.id}/download",
    }


def nome_seguro(filename: str) -> str:
    name = unicodedata.normalize("NFKC", filename).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    extension = Path(name).suffix.lower()
    stem = name[:-len(extension)] if extension else name
    return (stem[:180].strip(" .") or "arquivo") + extension


def formato(header: bytes) -> Optional[str]:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def caminho(c, key: str) -> Path:
    if not STORAGE_KEY.fullmatch(key):
        raise HTTPException(404, "Arquivo não encontrado")
    directory = Path(c.settings.arquivos_dir).resolve()
    path = directory / key
    # Também rejeita symlinks adulterados dentro do volume.
    if path.resolve().parent != directory or path.is_symlink():
        raise HTTPException(404, "Arquivo não encontrado")
    return path


def listar(rota_id: int) -> list[dict]:
    consultas.rota(rota_id)
    with sessao() as s:
        items = s.exec(select(ArquivoRota).where(ArquivoRota.rota_id == rota_id)
                       .order_by(ArquivoRota.id.desc())).all()
    return [metadados(item) for item in items]


def obter(c, rota_id: int, arquivo_id: int) -> tuple[ArquivoRota, Path]:
    consultas.rota(rota_id)
    with sessao() as s:
        item = s.get(ArquivoRota, arquivo_id)
    if not item or item.rota_id != rota_id:
        raise HTTPException(404, "Arquivo não encontrado")
    path = caminho(c, item.chave_storage)
    if not path.is_file():
        raise HTTPException(404, "Conteúdo do arquivo indisponível")
    return item, path


async def adicionar(c, rota_id: int, arquivo: UploadFile, categoria: str, descricao: Optional[str]) -> dict:
    consultas.rota(rota_id)
    name = nome_seguro(arquivo.filename or "")
    expected = EXTENSIONS.get(Path(name).suffix.lower())
    header = await arquivo.read(16)
    mime = formato(header)
    declared = arquivo.content_type
    if not mime or mime != expected or declared not in (mime, "application/octet-stream", None) and not (mime == "image/jpeg" and declared == "image/jpg"):
        raise HTTPException(415, "Use PDF, JPEG, PNG, WebP ou GIF com conteúdo correspondente")
    maximum = c.settings.arquivos_max_bytes
    if len(header) > maximum:
        raise HTTPException(413, "Arquivo excede o limite permitido")
    key = uuid.uuid4().hex + STORAGE_EXTENSION[mime]
    target = caminho(c, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    total = len(header)
    saved = False
    try:
        with temporary.open("xb") as stream:
            stream.write(header)
            while chunk := await arquivo.read(64 * 1024):
                total += len(chunk)
                if total > maximum:
                    raise HTTPException(413, "Arquivo excede o limite permitido")
                stream.write(chunk)
        temporary.replace(target)
        with sessao() as s:
            item = ArquivoRota(rota_id=rota_id, nome_original=name, tipo_mime=mime, tamanho_bytes=total,
                               categoria=categoria, descricao=descricao.strip() or None if descricao else None,
                               chave_storage=key)
            s.add(item)
            s.flush()
            event = Evento(rota_id=rota_id, tipo=TipoEvento.ARQUIVO_ADICIONADO, source="cco",
                           mensagem=f"Arquivo anexado: {name}",
                           dados={"arquivo_id": item.id, "nome_original": name, "categoria": categoria,
                                  "tipo_mime": mime, "tamanho_bytes": total})
            s.add(event)
            s.commit()
            saved = True
        c.eventos.publicar("evento", envelope(event), rota_id)
        return metadados(item)
    finally:
        temporary.unlink(missing_ok=True)
        if not saved:
            target.unlink(missing_ok=True)
        await arquivo.close()
