"""Adaptador `Transcritor`: OpenAI Audio Transcriptions (mesma chave e URL do LLM)."""
import httpx

from ..infra.settings import Settings


class OpenAITranscritor:
    def __init__(self, settings: Settings):
        self.s = settings

    async def transcrever(self, audio: bytes, nome: str, tipo_mime: str) -> str:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{self.s.llm_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                data={"model": self.s.stt_model, "language": "pt", "response_format": "json"},
                files={"file": (nome, audio, tipo_mime)},
            )
        if r.status_code >= 300:
            raise RuntimeError(f"transcrição falhou: HTTP {r.status_code} {r.text[:200]}")
        return (r.json().get("text") or "").strip()
