"""Tokens AccessToken2 via o SDK oficial (`agora-agents`; `agora-token` não existe no PyPI)."""
from agora_agent.agentkit.token import generate_client_token, generate_convo_ai_token, generate_rtc_token

from ..infra.settings import Settings

EXPIRA_S = 86400  # máximo aceito pela Agora


class CredencialAgoraInvalida(RuntimeError):
    pass


def _checar(s: Settings) -> None:
    if not s.agora_configurada():
        raise CredencialAgoraInvalida("Agora não configurada: defina AGORA_APP_ID e AGORA_APP_CERTIFICATE no .env")


def _gerar(fn, s: Settings, *args, **kw) -> str:
    _checar(s)
    try:
        return fn(s.agora_app_id, s.agora_app_certificate, *args, **kw)
    except ValueError as e:
        if "uid" in str(e).lower() and "32" not in str(e):
            raise
        raise CredencialAgoraInvalida(f"Credencial da Agora inválida: {e}") from None


def token_cliente(s: Settings, canal: str, uid: int) -> str:
    """RTC + RTM para app do motorista, painel do CCO e página do recebedor."""
    return _gerar(generate_client_token, s, canal, uid, token_expire=EXPIRA_S)


def token_agente(s: Settings, canal: str, uid: int) -> str:
    """RTC + RTM + ConvoAI: o agente entra no canal e autentica a REST (modo token)."""
    return _gerar(generate_convo_ai_token, s, canal, uid, token_expire=EXPIRA_S)


def token_rtc(s: Settings, canal: str, uid: int) -> str:
    """Só RTC (gateway SIP do plano A)."""
    return _gerar(generate_rtc_token, s, canal, uid, expiry_seconds=EXPIRA_S)
