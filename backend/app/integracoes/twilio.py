"""Adaptador mínimo de chamadas PSTN do Twilio.

Não há fallback silencioso: credenciais ausentes, erro HTTP e resposta inválida
voltam como resultado explícito para a decisão do agente.
"""
from dataclasses import dataclass
from xml.sax.saxutils import escape

import httpx


@dataclass(frozen=True)
class ResultadoTwilio:
    ok: bool
    detalhe: str
    sid: str | None = None


class TwilioGateway:
    def __init__(self, settings):
        self.settings = settings

    async def ligar(self, destino: str, motivo: str) -> ResultadoTwilio:
        if not self.settings.twilio_configurada():
            return ResultadoTwilio(False, "Twilio não configurado")
        texto = escape(f"Atenção do AvisAI. {motivo}".strip())[:1000]
        endpoint = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.settings.twilio_account_sid}/Calls.json"
        )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    endpoint,
                    auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
                    data={
                        "To": destino,
                        "From": self.settings.twilio_from_number,
                        "Twiml": f"<Response><Say language=\"pt-BR\">{texto}</Say></Response>",
                    },
                )
        except httpx.HTTPError as error:
            return ResultadoTwilio(False, f"Twilio indisponível: {error.__class__.__name__}")
        if response.status_code >= 300:
            return ResultadoTwilio(False, f"Twilio recusou a chamada (HTTP {response.status_code})")
        try:
            sid = response.json().get("sid")
        except ValueError:
            sid = None
        if not isinstance(sid, str) or not sid:
            return ResultadoTwilio(False, "Twilio respondeu sem identificador da chamada")
        return ResultadoTwilio(True, "chamada PSTN iniciada", sid)
