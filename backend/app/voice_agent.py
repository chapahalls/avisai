"""LiveKit worker com Gemini Live e ferramentas auditadas pelo gateway RODAR."""
import asyncio
import json
import logging
from typing import Any

import httpx
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RunContext, function_tool, inference
from livekit.agents.llm import ChatMessage

from .dominio import prompts
from .infra.settings import Settings
from .servicos import ferramentas

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rodar.voice_agent")
settings = Settings()
server = agents.AgentServer()


def _backend_headers(session_id: int) -> dict[str, str]:
    return {"x-avisai-sessao": str(session_id)}


def _model_tools(role: str, session_id: int, utterance: dict[str, str]) -> list[Any]:
    tools = []
    for name, item in ferramentas.para(role).items():
        wrapped = item.schema(name)["function"]
        schema = {
            "type": "function",
            "name": wrapped["name"],
            "description": wrapped["description"],
            "parameters": wrapped["parameters"],
        }

        def create_handler(tool_name: str, raw_schema: dict[str, Any]):
            @function_tool(raw_schema=raw_schema)
            async def execute(raw_arguments: dict[str, object], context: RunContext) -> str:
                base = settings.livekit_llm_url.rstrip("/")
                try:
                    async with httpx.AsyncClient(timeout=60) as client:
                        response = await client.post(
                            f"{base}/voice/tool",
                            headers=_backend_headers(session_id),
                            json={
                                "name": tool_name,
                                "arguments": raw_arguments,
                                "utterance": utterance["text"],
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                except Exception as exc:  # noqa: BLE001
                    log.exception("ferramenta %s falhou no gateway", tool_name)
                    result = {"ok": False, "erro": str(exc)}
                return json.dumps(result, ensure_ascii=False, default=str)

            return execute

        tools.append(create_handler(name, schema))
    return tools


def _instrucoes(metadata: dict[str, Any]) -> str:
    instructions = metadata.get("instructions", "Converse em português do Brasil.")
    terms = list(dict.fromkeys(
        [*settings.asr_keywords, *(str(term).strip() for term in metadata.get("asr_keyterms", []) if str(term).strip())]
    ))
    instructions += "\n\nVocabulário importante desta operação: " + ", ".join(terms) + "."
    if settings.filler_words:
        phrases = " / ".join(settings.filler_words)
        instructions += (
            f"\nSe uma ferramenta levar mais de {settings.filler_espera_ms} ms, mantenha a conversa natural "
            f"com uma frase curta enquanto aguarda, escolhida entre: {phrases}."
        )
    return instructions


def _metadata(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def accept_job(req: agents.JobRequest) -> None:
    metadata = _metadata(req.job.metadata)
    # Sessões do backend mandam a identidade; o despacho pelo token do teste ao vivo vem sem metadata.
    identity = metadata.get("agent_identity") or f"agente-{req.room.name}"
    await req.accept(name="RODAR", identity=identity)


async def demo_ao_vivo(ctx: agents.JobContext) -> None:
    """Sala do teste ao vivo (POST /livekit/token): conversa sem rota, sem ferramentas e sem sincronizar com o backend."""
    instructions, greeting = prompts.demo_ao_vivo()
    session = AgentSession(
        llm=inference.RealtimeModel(model=settings.livekit_model, voice=settings.livekit_voice),
        user_away_timeout=None,
    )
    await session.start(room=ctx.room, agent=Agent(instructions=_instrucoes({"instructions": instructions})))
    await ctx.wait_for_participant()
    await session.generate_reply(
        instructions=(
            "Cumprimente o usuário dizendo exatamente o texto entre as tags <mensagem>. "
            f"Não acrescente nem altere palavras. <mensagem>{greeting}</mensagem>"
        ),
        allow_interruptions=True,
    )


@server.rtc_session(agent_name=settings.livekit_agent_name, on_request=accept_job)
async def voice_agent(ctx: agents.JobContext) -> None:
    metadata = _metadata(ctx.job.metadata)
    if "session_id" not in metadata:
        log.info("despacho sem sessão do backend: modo demo na sala %s", ctx.room.name)
        await ctx.connect()
        await demo_ao_vivo(ctx)
        return
    session_id = int(metadata["session_id"])
    role = str(metadata["role"])
    base = settings.livekit_llm_url.rstrip("/")
    headers = _backend_headers(session_id)
    await ctx.connect()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base}/voice/context", headers=headers)
        response.raise_for_status()
        state = response.json().get("state", "")

    base_instructions = _instrucoes(metadata)
    instructions = f"{base_instructions}\n\nSITUAÇÃO ATUAL DA OPERAÇÃO:\n{state}"
    utterance = {"text": ""}
    agent = Agent(instructions=instructions, tools=_model_tools(role, session_id, utterance))
    session = AgentSession(
        llm=inference.RealtimeModel(model=settings.livekit_model, voice=settings.livekit_voice),
        user_away_timeout=None,
    )
    await session.start(room=ctx.room, agent=agent)

    def on_conversation_item(event) -> None:
        item = event.item
        if not isinstance(item, ChatMessage) or item.role not in ("user", "assistant"):
            return
        text = item.text_content.strip()
        if not text:
            return
        if item.role == "user":
            utterance["text"] = text

        async def sync_turn() -> None:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    result = await client.post(
                        f"{base}/voice/turn",
                        headers=headers,
                        json={"role": item.role, "text": text},
                    )
                    result.raise_for_status()
                    if item.role == "user":
                        current_state = result.json().get("state", "")
                        await agent.update_instructions(
                            f"{base_instructions}\n\nSITUAÇÃO ATUAL DA OPERAÇÃO:\n{current_state}"
                        )
            except Exception:  # noqa: BLE001
                log.exception("não foi possível sincronizar a fala com o backend: session=%s", session_id)

        asyncio.create_task(sync_turn())

    session.on("conversation_item_added", on_conversation_item)
    speech_lock = asyncio.Lock()

    def on_data(packet: rtc.DataPacket) -> None:
        if packet.topic != "rodar.control":
            return
        try:
            command = json.loads(packet.data.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("comando de sala inválido: room=%s", ctx.room.name)
            return
        if command.get("action") != "speak" or not command.get("text"):
            return

        async def speak() -> None:
            async with speech_lock:
                priority = str(command.get("priority", "APPEND")).upper()
                if priority == "INTERRUPT":
                    await session.interrupt(force=True)
                elif session.current_speech is not None:
                    await session.current_speech.wait_for_playout()
                await session.generate_reply(
                    instructions=(
                        "Diga ao usuário exatamente o texto entre as tags <mensagem>, em português do Brasil. "
                        "Não acrescente explicações nem altere o conteúdo. "
                        f"<mensagem>{command['text']}</mensagem>"
                    ),
                    allow_interruptions=True,
                )

        asyncio.create_task(speak())

    ctx.room.on("data_received", on_data)
    await ctx.wait_for_participant()
    greeting = str(metadata.get("greeting", "")).strip()
    if greeting:
        await session.generate_reply(
            instructions=(
                "Cumprimente o usuário dizendo exatamente o texto entre as tags <mensagem>. "
                "Não acrescente nem altere palavras. "
                f"<mensagem>{greeting}</mensagem>"
            ),
            allow_interruptions=True,
        )


if __name__ == "__main__":
    agents.cli.run_app(server)
