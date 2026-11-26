/**
 * Contrato do backend AvisAI para os fronts (espelho de backend/app/api/schemas.py e dos enums).
 * Fonte de verdade: GET {API}/openapi.json (dá para gerar com `npx openapi-typescript`).
 */

export type StatusTask = "pendente" | "confirmada" | "escalada_recebedor" | "concluida";
export type StatusRota = "publicada" | "planejada" | "na_origem" | "em_transito" | "aproximando" | "no_destino" | "descarregada";
export type StatusLigacao = "chamando" | "em_andamento" | "respondida" | "nao_atendida" | "falhou";

export type TipoEvento =
  | "sessao_iniciada" | "aproximacao" | "chegada" | "chegada_confirmada_voz"
  | "notificacao_cco" | "escalada_recebedor" | "task_confirmada"
  | "ligacao_recebedor" | "ligacao_falhou" | "fallback_plano_b" | "ligacao_nao_atendida" | "resposta_recebedor"
  | "ocorrencia" | "descarga" | "fala_motorista" | "fala_recebedor" | "fala_agente"
  | "retirada_detectada" | "retirada" | "relatorio" | "campo_faltante" | "task_criada" | "aviso_recebedor"
  | "nao_recebe_hoje" | "pedido_central" | "resposta_central" | "divergencia_gps" | "rota_publicada" | "rota_atribuida"
  | "pergunta_documento" | "chamado_cco_aberto" | "chamado_cco_lembrete" | "chamado_cco_respondido" | "chamado_cco_timeout"
  | "alerta_motorista" | "decisao_agente"
  | "mensagem_motorista_enviada" | "mensagem_motorista_falada" | "mensagem_motorista_respondida" | "motorista_offline"
  | "chamada_twilio_falhou" | "chamada_livekit_iniciada" | "chamada_livekit_atendida" | "chamada_sem_resposta" | "escalada_supervisor";

export interface Sessao {
  id: number;
  rota_id: number;
  papel: "motorista" | "recebedor" | "operador";
  canal: string;
  agent_id: string | null;
  status: "iniciando" | "ativa" | "encerrada" | "falhou";
  llm_mode: string;
  livekit_url: string | null;
  identity: string | null;
  token: string | null;
  erro?: string | null;
}

export interface EventoStream {
  id: number;
  tipo: TipoEvento;
  rota_id: number | null;
  timestamp: string;
  mensagem: string;
  dados: Record<string, unknown>;
}

export interface TaskCCO {
  id: number;
  rota_id: number;
  tipo: string;
  status: StatusTask;
  prioridade: "normal" | "alta" | "critica";
  tentativas: number;
  canal_atual: "push" | "painel" | "ligacao" | null;
  criada_em: string;
  ultima_notificacao: string | null;
  confirmado_em: string | null;
  confirmado_por: string | null;
  resposta_recebedor: string | null;
  concluida_em: string | null;
}

export interface Estadia {
  estadia_id: number;
  rota_id: number;
  inicio: string;
  fim: string | null;
  encerrada: boolean;
  horas_paradas: number;
  tempo_parado: string; // "4h05"
  franquia_h: number;
  franquia_restante_h: number;
  franquia_restante: string;
  horas_excedentes: number;
  capacidade_t: number;
  valor_t_h: number;
  valor: number;
  valor_fmt: string; // "R$ 140,00"
}

export interface Ligacao {
  id: number;
  rota_id: number;
  task_id: number | null;
  motivo: "aproximacao" | "cco_sem_resposta";
  modo: "rtc" | "sip";
  numero: string;
  canal: string | null;
  status: StatusLigacao;
  atendida: boolean;
  previsao: string | null;
  doca: string | null;
  motivo_espera: string | null;
  resposta_resumo: string | null;
  transcricao: { quem: "recebedor" | "agente"; texto: string; ts: number }[];
}

export interface ChamadoCCO {
  id: number;
  rota_id: number;
  tipo: string;
  assunto: string;
  descricao: string;
  km: number | null;
  rodovia: string | null;
  ocorrencia_id: number | null;
  status: "coletando" | "aguardando_cco" | "respondido" | "timeout";
  tentativas: number;
  max_tentativas: number;
  intervalo_s: number;
  criada_em: string;
  ultima_notificacao: string | null;
  respondida_em: string | null;
  resposta: string | null;
  respondido_por: string | null;
  transcricao: string | null;
}

export interface Rota {
  id: number;
  status: StatusRota;
  placa: string;
  nota_fiscal: string;
  carga_descricao: string;
  carga_t: number;
  origem_nome: string;
  destino_nome: string;
  destino_lat: number;
  destino_lng: number;
  ultima_lat: number | null;
  ultima_lng: number | null;
  distancia_m: number | null;
  eta_min: number | null;
  recebedor_empresa: string;
  recebedor_nome: string;
  motorista_nome: string | null;
  canal_motorista: string;
}

export interface Snapshot {
  rotas: Rota[];
  tasks: TaskCCO[];
  estadias: Estadia[];
  ligacoes: Ligacao[];
  ocorrencias: { id: number; rota_id: number; tipo: string; descricao: string; timestamp: string }[];
  eventos: EventoStream[];
  chamados?: ChamadoCCO[];
}

/** Mensagens do SSE (/cco/stream, `event:`) e do WS (/ws, campo `canal`). */
export interface MensagensStream {
  snapshot: Snapshot;
  evento: EventoStream;
  task: { task: TaskCCO };
  posicao: { rota_id: number; lat: number; lng: number; distancia_m: number; eta_min: number; status: StatusRota };
  fala: { rota_id: number; papel: "motorista" | "recebedor" | "operador"; texto: string };
  contador: { estadias: Estadia[] };
  reset: { rota_id: number };
  chamado: { chamado: ChamadoCCO };
}
export type CanalStream = keyof MensagensStream;
export const CANAIS: CanalStream[] = ["snapshot", "evento", "task", "posicao", "fala", "contador", "reset", "chamado"];
