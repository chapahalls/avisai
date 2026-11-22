"""Limita o corpo de upload antes de o parser multipart armazená-lo."""
import re
from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse

from . import container


class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not re.fullmatch(r"/rotas/[^/]+/arquivos/?", scope.get("path", "")):
            return await self.app(scope, receive, send)
        # Margem limitada para cabeçalhos multipart e os dois campos opcionais.
        maximum = container.atual().settings.arquivos_max_bytes + 64 * 1024
        length = dict(scope.get("headers", [])).get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > maximum
            except ValueError:
                return await JSONResponse({"detail": "Content-Length inválido"}, status_code=400)(scope, receive, send)
            if too_large:
                return await JSONResponse({"detail": "Arquivo excede o limite permitido"}, status_code=413)(scope, receive, send)
        consumed = 0
        # Valida inclusive transferências sem Content-Length. O spool é fechado mesmo
        # no abort; o parser não recebe um corpo ilimitado nem um arquivo parcial.
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                chunk = message.get("body", b"")
                consumed += len(chunk)
                if consumed > maximum:
                    return await JSONResponse({"detail": "Arquivo excede o limite permitido"}, status_code=413)(scope, receive, send)
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)

            async def replay():
                chunk = body.read(64 * 1024)
                return {"type": "http.request", "body": chunk, "more_body": body.tell() < consumed}

            await self.app(scope, replay, send)
