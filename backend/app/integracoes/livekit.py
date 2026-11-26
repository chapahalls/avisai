"""Cliente de servidor LiveKit: tokens, dispatch de agentes, salas e telefonia SIP."""
import json
import logging
from datetime import timedelta
from typing import Any

from livekit import api, rtc

from ..infra.settings import Settings

log = logging.getLogger("rodar.livekit")


class LiveKitErro(RuntimeError):
    def __init__(self, status: int, corpo: str):
        super().__init__(f"LiveKit HTTP {status}: {corpo}")
        self.status = status
        self.corpo = corpo


def url_http(url: str) -> str:
    return url.replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")


def token(s: Settings, room: str, identity: str, *, publish: bool = True, subscribe: bool = True,
          publish_data: bool = False, name: str | None = None, ttl: int = 3600) -> str:
    if not s.livekit_configurada():
        raise RuntimeError("LiveKit não configurado: defina LIVEKIT_URL, LIVEKIT_API_KEY e LIVEKIT_API_SECRET")
    grants = api.VideoGrants(room_join=True, room=room, can_publish=publish,
                             can_subscribe=subscribe, can_publish_data=publish_data)
    access = api.AccessToken(s.livekit_api_key, s.livekit_api_secret)
    access.with_identity(identity).with_grants(grants).with_ttl(timedelta(seconds=ttl))
    if name:
        access.with_name(name)
    return access.to_jwt()


class LiveKitGateway:
    def __init__(self, settings: Settings):
        self.s = settings

    def _client(self):
        if not self.s.livekit_configurada():
            raise RuntimeError("LiveKit não configurado: defina LIVEKIT_URL, LIVEKIT_API_KEY e LIVEKIT_API_SECRET")
        return api.LiveKitAPI(self.s.livekit_url, self.s.livekit_api_key, self.s.livekit_api_secret)

    async def dispatch(self, room: str, metadata: dict[str, Any]) -> str:
        async with self._client() as lk:
            info = await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                agent_name=self.s.livekit_agent_name,
                room=room,
                metadata=json.dumps(metadata, ensure_ascii=False),
            ))
            return info.id

    async def remove(self, room: str, identity: str) -> None:
        async with self._client() as lk:
            try:
                await lk.room.remove_participant(api.RemoveParticipantRequest(room=room, identity=identity))
            except Exception as exc:
                # Removal is idempotent from the application's perspective.
                if "not found" not in str(exc).lower() and "404" not in str(exc):
                    raise

    async def send_control(self, room: str, identity: str, message: dict[str, Any]) -> None:
        # Server data packets use the RTC SDK so we do not depend on generated
        # protobuf enum names across livekit-api releases.
        control_identity = f"rodar-control-{identity}"
        control_token = token(self.s, room, control_identity, publish=False, subscribe=False, publish_data=True)
        client = rtc.Room()
        try:
            await client.connect(self.s.livekit_url, control_token)
            await client.local_participant.publish_data(
                json.dumps(message, ensure_ascii=False).encode(),
                reliable=True,
                destination_identities=[identity],
                topic="rodar.control",
            )
        finally:
            await client.disconnect()

    async def dial(self, room: str, number: str, identity: str, *, wait: bool = False) -> str:
        if not self.s.livekit_sip_trunk_id:
            raise RuntimeError("LIVEKIT_SIP_TRUNK_ID não configurado")
        async with self._client() as lk:
            participant = await lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                sip_trunk_id=self.s.livekit_sip_trunk_id,
                sip_call_to=number,
                sip_number=self.s.livekit_sip_from_number or "",
                room_name=room,
                participant_identity=identity,
                participant_name="RODAR",
                wait_until_answered=wait,
            ), timeout=self.s.chamada_operador_timeout_s if wait else None)
            return participant.participant_identity or identity

    async def participant_present(self, room: str, identity: str) -> bool:
        async with self._client() as lk:
            response = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
            return any(p.identity == identity for p in response.participants)

    async def sip_call_status(self, room: str, identity: str) -> str | None:
        async with self._client() as lk:
            response = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
            participant = next((p for p in response.participants if p.identity == identity), None)
            if participant is None:
                return None
            return participant.attributes.get("sip.callStatus") or None
