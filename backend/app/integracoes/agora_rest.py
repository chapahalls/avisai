"""Adaptador `AgoraGateway`: REST da Conversational AI v2 (payloads do OpenAPI oficial).

Usamos REST direto em vez do builder do SDK porque o SDK 2.15 força
`turn_detection.language`/`asr.language` = en-US e não aceita pt-BR.
"""
import base64
import logging

import httpx

from ..infra.settings import Settings
from . import tokens

log = logging.getLogger("avisai.agora")


class AgoraErro(RuntimeError):
    def __init__(self, status: int, corpo: str):
        super().__init__(f"Agora HTTP {status}: {corpo}")
        self.status = status
        self.corpo = corpo


class AgoraRest:
    def __init__(self, settings: Settings):
        self.s = settings

    def _url(self, caminho: str) -> str:
        return f"{self.s.agora_api_base.rstrip('/')}/v2/projects/{self.s.agora_app_id}{caminho}"

    def _headers(self, canal: str, agent_uid: int) -> dict:
        if self.s.agora_customer_id and self.s.agora_customer_secret:
            cred = f"{self.s.agora_customer_id}:{self.s.agora_customer_secret}".encode()
            auth = "Basic " + base64.b64encode(cred).decode()
        else:
            auth = "agora token=" + tokens.token_agente(self.s, canal, agent_uid)
        return {"Authorization": auth, "Content-Type": "application/json"}

    async def _req(self, metodo: str, caminho: str, canal: str, agent_uid: int, corpo: dict | None = None, ok404: bool = False) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.request(metodo, self._url(caminho), json=corpo, headers=self._headers(canal, agent_uid))
        except httpx.HTTPError as e:  # DNS, conexão, timeout: vira AgoraErro, que os serviços tratam
            log.error("Agora %s %s -> falha de rede: %s", metodo, caminho, e)
            raise AgoraErro(503, f"falha de rede: {e}") from e
        if ok404 and r.status_code == 404:
            return {}
        if r.status_code >= 300:
            log.error("Agora %s %s -> %s %s", metodo, caminho, r.status_code, r.text[:500])
            raise AgoraErro(r.status_code, r.text[:1000])
        try:
            return r.json()
        except ValueError:
            return {}

    @staticmethod
    def _canal_uid(corpo: dict) -> tuple[str, int]:
        p = corpo["properties"]
        return p["channel"], int(p["agent_rtc_uid"])

    async def join(self, corpo: dict) -> str:
        canal, uid = self._canal_uid(corpo)
        return (await self._req("POST", "/join", canal, uid, corpo))["agent_id"]

    async def leave(self, agent_id: str, canal: str, agent_uid: int) -> None:
        await self._req("POST", f"/agents/{agent_id}/leave", canal, agent_uid, {}, ok404=True)

    async def speak(self, agent_id: str, texto: str, prioridade: str, canal: str, agent_uid: int) -> None:
        t = texto.encode("utf-8")[:512].decode("utf-8", "ignore")
        await self._req("POST", f"/agents/{agent_id}/speak", canal, agent_uid,
                        {"text": t, "priority": prioridade, "interruptable": True})

    async def call(self, corpo: dict) -> str:
        canal, uid = self._canal_uid(corpo)
        return (await self._req("POST", "/call", canal, uid, corpo))["agent_id"]

    async def call_status(self, agent_id: str, canal: str, agent_uid: int) -> dict:
        return await self._req("GET", f"/calls/{agent_id}", canal, agent_uid)

    async def hangup(self, agent_id: str, canal: str, agent_uid: int) -> None:
        await self._req("POST", f"/calls/{agent_id}/hangup", canal, agent_uid, {}, ok404=True)
