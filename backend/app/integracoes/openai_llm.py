"""Adaptador `LLM`: OpenAI Chat Completions com streaming e ferramentas.

`stream` produz eventos: {"texto": "..."} conforme chegam, ou um {"tool_calls": [...]}
completo quando o modelo decide chamar ferramentas.
"""
import json
import logging
from typing import AsyncIterator

import httpx

from ..infra.settings import Settings

log = logging.getLogger("avisai.llm")


class OpenAILLM:
    def __init__(self, settings: Settings):
        self.s = settings

    async def stream(self, mensagens: list[dict], ferramentas: list[dict]) -> AsyncIterator[dict]:
        corpo = {
            "model": self.s.llm_model,
            "messages": mensagens,
            "stream": True,
            "temperature": 0.4,
            "max_tokens": self.s.llm_max_tokens,
        }
        if ferramentas:
            corpo["tools"] = ferramentas
            corpo["tool_choice"] = "auto"
        calls: dict[int, dict] = {}
        async with httpx.AsyncClient(timeout=30) as c:
            async with c.stream(
                "POST",
                f"{self.s.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                json=corpo,
            ) as r:
                if r.status_code >= 300:
                    txt = (await r.aread()).decode()[:300]
                    raise RuntimeError(f"LLM upstream {r.status_code}: {txt}")
                async for linha in r.aiter_lines():
                    if not linha.startswith("data: "):
                        continue
                    dado = linha[6:].strip()
                    if dado == "[DONE]":
                        break
                    ch = json.loads(dado)
                    if not ch.get("choices"):
                        continue
                    delta = ch["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        yield {"texto": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        i = tc.get("index", 0)
                        atual = calls.setdefault(i, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            atual["id"] = tc["id"]
                        f = tc.get("function") or {}
                        atual["function"]["name"] += f.get("name") or ""
                        atual["function"]["arguments"] += f.get("arguments") or ""
        if calls:
            yield {"tool_calls": [calls[i] for i in sorted(calls)]}
