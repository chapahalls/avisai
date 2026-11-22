"""Descobre a URL pública: PUBLIC_URL do .env ou o quick tunnel do cloudflared (/quicktunnel)."""
import logging

import httpx

log = logging.getLogger("avisai.tunel")


def url_publica(settings=None) -> str:
    from ..infra import container as ct

    s = settings or ct.atual().settings
    if s.public_url:
        return s.public_url.rstrip("/")
    if s.tunnel_metrics_url:
        try:
            r = httpx.get(f"{s.tunnel_metrics_url.rstrip('/')}/quicktunnel", timeout=3)
            host = r.json().get("hostname")
            if host:
                return f"https://{host}"
        except Exception as e:  # noqa: BLE001
            log.warning("não consegui ler a URL do túnel: %s", e)
    return ""
