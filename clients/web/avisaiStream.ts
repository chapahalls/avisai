/**
 * Cliente do painel do CCO (Vite, sem framework): SSE tipado + ações REST.
 * Copie `clients/tipos.ts` e este arquivo. Para React, veja `useAvisaiCCO.ts`.
 *
 *   const cco = new AvisaiStream(import.meta.env.VITE_AVISAI_API);
 *   cco.on("task", ({ task }) => ...);
 *   cco.on("contador", ({ estadias }) => ...);
 *   cco.conectar();
 *   await cco.confirmarTask(task.id, "Ana (CCO)");
 */
import { CANAIS, type CanalStream, type MensagensStream, type Snapshot, type TaskCCO } from "../tipos";

type Ouvinte<K extends CanalStream> = (dado: MensagensStream[K]) => void;
export type StatusConexao = "desconectado" | "conectando" | "conectado";

export class AvisaiStream {
  readonly base: string;
  private es: EventSource | null = null;
  private ouvintes = new Map<CanalStream, Set<(dado: unknown) => void>>();
  private religar?: ReturnType<typeof setTimeout>;
  private ativo = false;
  status: StatusConexao = "desconectado";
  onStatus?: (s: StatusConexao) => void;

  constructor(api: string, private rotaId?: number) {
    this.base = api.replace(/\/$/, "");
  }

  on<K extends CanalStream>(canal: K, fn: Ouvinte<K>): () => void {
    let set = this.ouvintes.get(canal);
    if (!set) this.ouvintes.set(canal, (set = new Set()));
    const f = fn as (dado: unknown) => void;
    set.add(f);
    return () => set.delete(f);
  }

  conectar(): void {
    this.ativo = true;
    this.abrir();
  }

  fechar(): void {
    this.ativo = false;
    clearTimeout(this.religar);
    this.es?.close();
    this.es = null;
    this.mudar("desconectado");
  }

  private mudar(s: StatusConexao) {
    this.status = s;
    this.onStatus?.(s);
  }

  private abrir() {
    this.es?.close();
    this.mudar("conectando");
    const q = this.rotaId ? `?rota_id=${this.rotaId}` : "";
    const es = new EventSource(`${this.base}/cco/stream${q}`);
    this.es = es;
    es.onopen = () => this.mudar("conectado");
    for (const canal of CANAIS) {
      es.addEventListener(canal, (e) => {
        const dado = JSON.parse((e as MessageEvent<string>).data);
        this.ouvintes.get(canal)?.forEach((fn) => fn(dado));
      });
    }
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED && this.ativo) {
        this.mudar("conectando");
        this.religar = setTimeout(() => this.abrir(), 2000);
      }
    };
  }

  // ---------- REST ----------
  private async req<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
    const r = await fetch(`${this.base}${caminho}`, {
      method: metodo,
      headers: corpo ? { "Content-Type": "application/json" } : undefined,
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    return (await r.json()) as T;
  }

  estado(): Promise<Snapshot> {
    return this.req("GET", `/cco/estado${this.rotaId ? `?rota_id=${this.rotaId}` : ""}`);
  }

  /** CCO assume a Task: para o escalonamento e o agente avisa o motorista. */
  confirmarTask(taskId: number, confirmadoPor = "CCO"): Promise<TaskCCO> {
    return this.req("POST", `/tasks/${taskId}/confirmar`, { confirmado_por: confirmadoPor });
  }

  /** CCO confirma a descarga: encerra a estadia e a Task. */
  confirmarDescarga(rotaId: number, por = "CCO"): Promise<unknown> {
    return this.req("POST", `/rotas/${rotaId}/descarga`, { por });
  }

  /** Atalho de demo: liga para o recebedor agora. */
  ligarRecebedor(rotaId: number): Promise<unknown> {
    return this.req("POST", `/rotas/${rotaId}/ligar-recebedor`, { motivo: "cco_sem_resposta" });
  }

  resetDemo(rotaId: number): Promise<unknown> {
    return this.req("POST", `/rotas/${rotaId}/reset`);
  }

  /** Token para uma identidade da sala LiveKit. */
  token(room: string, identity: string): Promise<{ url: string; room: string; identity: string; token: string }> {
    return this.req("GET", `/token?room=${encodeURIComponent(room)}&identity=${encodeURIComponent(identity)}`);
  }
}
