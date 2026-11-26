"""Configuração. Em Docker vem do .env (env_file do compose)."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

FILLER_PADRAO = [
    "Só um instante, tô vendo aqui.",
    "Peraí, deixa eu registrar.",
    "Um segundinho, parceiro.",
]


class Settings(BaseSettings):
    # LiveKit: transporte WebRTC, dispatch do agente e telefonia SIP.
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "rodar-voice-agent"
    livekit_llm_url: str = "http://api:8000/v1"
    livekit_model: str = "google/gemini-3.8-live"
    livekit_voice: str = "Charon"
    # Vocabulário da operação incluído nas instruções do modelo realtime.
    asr_keywords: list[str] = [
        "AvisAI", "doca", "portaria", "pátio", "descarga", "descarreguei", "estadia", "franquia", "recebimento",
        "recebedor", "CCO", "central", "nota fiscal", "NF-e", "CT-e", "DANFE", "palete", "paletes", "toneladas",
        "lacre", "canhoto", "avaria", "retirada", "check-in", "ocorrência", "fila", "placa", "frete",
    ]
    filler_words: list[str] = FILLER_PADRAO
    filler_espera_ms: int = 1500

    # Ligação ao recebedor: rtc (plano B, navegador) | sip (plano A, telefone)
    recebedor_modo: str = "rtc"
    livekit_sip_trunk_id: str = ""
    livekit_sip_from_number: str = ""
    recebedor_telefone_e164: str = "+5519900000002"

    # Telefonia do agente: Twilio PSTN é a primeira tentativa; LiveKit RTC atende no navegador.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_operator_phone_e164: str = ""
    twilio_supervisor_phone_e164: str = ""
    chamada_operador_timeout_s: float = 30

    # O agente usa este gateway para executar ferramentas e registrar eventos no backend.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 150
    llm_shared_secret: str = ""

    # Acesso: token JWT assinado no /auth/sso. Ligado por padrão: escrita exige token, ações da central exigem
    # papel "cco" e o motorista só mexe na própria rota. Desligue (AUTH_OBRIGATORIA=false) só em desenvolvimento.
    auth_obrigatoria: bool = True
    auth_segredo: str = ""
    auth_token_validade_h: float = 12
    # Origens permitidas no CORS (painel web). "*" libera tudo; use só em desenvolvimento.
    cors_origens: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173",
        "http://localhost:8081", "http://localhost:19006",
    ]
    # Ligações disparadas à mão (CCO, atalhos de demo): no máximo N por rota a cada janela. 0 desliga.
    ligacoes_manuais_max: int = 5
    ligacoes_manuais_janela_s: float = 600

    # Público / túnel
    public_url: str = ""
    tunnel_metrics_url: str = ""

    # Banco
    database_url: str = "postgresql+psycopg://avisai:avisai@db:5432/avisai"

    # Arquivos da viagem: conteúdo persistente, separado dos documentos fiscais fictícios.
    arquivos_dir: str = "data/arquivos"
    arquivos_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    # Falas gravadas sem sinal (offline-first): o app guarda o áudio e manda quando a rede volta.
    falas_offline_dir: str = "data/falas_offline"
    falas_offline_max_bytes: int = Field(default=5 * 1024 * 1024, gt=0, le=50 * 1024 * 1024)
    stt_model: str = "gpt-4o-mini-transcribe"  # transcrição na API do LLM (mesma chave e URL)
    fuso_utc_horas: int = -3  # horário falado ao motorista (Brasília, sem horário de verão)

    # Ritmo da demo
    cco_intervalo_s: float = 20
    cco_max_tentativas: int = 3
    chamado_cco_intervalo_s: float = 30
    chamado_cco_max_tentativas: int = 5
    estadia_aceleracao: float = 1
    estadia_valor_t_h: float = 2.50
    estadia_franquia_h: float = 5
    ligar_recebedor_na_aproximacao: bool = True  # fluxo do repo de ideias: avisa o recebedor antes de chegar
    ligacao_timeout_s: float = 180
    ligacao_poll_s: float = 5
    encerrar_ligacao_apos_s: float = 20
    velocidade_padrao_kmh: float = 60
    divergencia_gps_max_m: float = 500
    model_config = SettingsConfigDict(extra="ignore", env_file=None, populate_by_name=True)

    def livekit_configurada(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    def twilio_configurada(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)
