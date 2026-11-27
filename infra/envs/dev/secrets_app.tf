# Secrets com valor placeholder — preenche os de verdade depois do apply via
# `aws secretsmanager put-secret-value` (não tem valor real pra essas
# integrações aqui). O OpenTofu ignora mudança no conteúdo pra não sobrescrever
# o que for preenchido manualmente.

locals {
  app_secrets = {
    livekit = {
      name = "rumolog/dev/livekit"
      desc = "Credenciais LiveKit (voz) do rodar-backend."
      placeholder = {
        LIVEKIT_URL             = "wss://CHANGE_ME.livekit.cloud"
        LIVEKIT_API_KEY         = "CHANGE_ME"
        LIVEKIT_API_SECRET      = "CHANGE_ME"
        LIVEKIT_AGENT_NAME      = "rodar-voice-agent"
        LIVEKIT_SIP_TRUNK_ID    = ""
        LIVEKIT_SIP_FROM_NUMBER = ""
        LIVEKIT_MODEL           = "google/gemini-3.8-live"
        LIVEKIT_VOICE           = "Charon"
      }
    }
    llm = {
      name = "rumolog/dev/llm"
      desc = "Credenciais do LLM (OpenAI-compatível) do rodar-backend."
      placeholder = {
        LLM_API_KEY  = "CHANGE_ME"
        LLM_BASE_URL = "https://api.openai.com/v1"
        LLM_MODEL    = "gpt-4o-mini"
      }
    }
    auth = {
      name = "rumolog/dev/auth"
      desc = "Segredo de assinatura JWT (AUTH_SEGREDO) do rodar-backend."
      placeholder = {
        AUTH_SEGREDO = "CHANGE_ME"
      }
    }
    twilio = {
      name = "rumolog/dev/twilio"
      desc = "Credenciais Twilio (ligação PSTN do agente) do rodar-backend."
      placeholder = {
        TWILIO_ACCOUNT_SID           = "CHANGE_ME"
        TWILIO_AUTH_TOKEN            = "CHANGE_ME"
        TWILIO_FROM_NUMBER           = ""
        TWILIO_OPERATOR_PHONE_E164   = ""
        TWILIO_SUPERVISOR_PHONE_E164 = ""
      }
    }
  }
}

resource "aws_secretsmanager_secret" "app" {
  for_each = local.app_secrets

  name                    = each.value.name
  description             = each.value.desc
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each = local.app_secrets

  secret_id     = aws_secretsmanager_secret.app[each.key].id
  secret_string = jsonencode(each.value.placeholder)

  lifecycle {
    ignore_changes = [secret_string]
  }
}
