/**
 * Hook do app do motorista (React Native): conversa por voz com o agente AvisAI.
 *
 * Copie `clients/tipos.ts` e este arquivo para o app.
 * Dependências: `@livekit/react-native` e `livekit-client`. Tem módulo nativo:
 * precisa de dev build ou `expo prebuild` (não roda no Expo Go).
 * Permissões: Android RECORD_AUDIO (pedida aqui), iOS NSMicrophoneUsageDescription no Info.plist.
 *
 *   const voz = useAvisaiVoz({ api: "https://xxxx.trycloudflare.com", rotaId: 1 });
 *   <Button title="Falar com o AvisAI" onPress={voz.iniciar} />
 *   <Text>{voz.status} · {voz.estadia?.tempo_parado} · {voz.estadia?.valor_fmt}</Text>
 *
 * Só controle e mídia: o áudio vai do celular direto para a sala LiveKit; o backend despacha o agente.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { PermissionsAndroid, Platform } from "react-native";
import { AudioSession } from "@livekit/react-native";
import { Room, RoomEvent } from "livekit-client";

import type { EventoStream, Estadia, Ligacao, MensagensStream, Sessao, TaskCCO } from "../tipos";

export type StatusVoz =
  | "parado" // sem sessão
  | "conectando" // criando o agente / entrando no canal
  | "aguardando_agente" // na sala, esperando o agente entrar
  | "conversando" // agente no canal: pode falar (e interromper)
  | "erro";

export interface FalaAgente {
  texto: string;
  em: number;
}

export interface OpcoesVoz {
  api: string; // URL pública do backend (PUBLIC_URL do túnel)
  rotaId: number;
  /** Se informado, o WS acompanha as rotas do motorista e avisa quando uma rota nova for atribuída. */
  motoristaId?: number;
  /** Chamado quando a transportadora atribui uma rota nova a este motorista (RouteAssigned). */
  onRotaAtribuida?: (rotaId: number) => void;
  /** Quantos eventos manter em memória (padrão 50). */
  maxEventos?: number;
}

async function pedirMicrofone(): Promise<boolean> {
  if (Platform.OS !== "android") return true;
  const r = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
  return r === PermissionsAndroid.RESULTS.GRANTED;
}

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  return (await r.json()) as T;
}

export function useAvisaiVoz({ api, rotaId, motoristaId, onRotaAtribuida, maxEventos = 50 }: OpcoesVoz) {
  const base = api.replace(/\/$/, "");
  const [status, setStatus] = useState<StatusVoz>("parado");
  const [erro, setErro] = useState<string | null>(null);
  const [sessao, setSessao] = useState<Sessao | null>(null);
  const [mudo, setMudo] = useState(false);
  const [eventos, setEventos] = useState<EventoStream[]>([]);
  const [falas, setFalas] = useState<FalaAgente[]>([]);
  const [estadia, setEstadia] = useState<Estadia | null>(null);
  const [task, setTask] = useState<TaskCCO | null>(null);
  const [ligacao, setLigacao] = useState<Ligacao | null>(null);

  const roomRef = useRef<Room | null>(null);
  const sessaoRef = useRef<Sessao | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const vivoRef = useRef(true);

  // ---------- WebSocket com eventos da rota (legenda, contador, Task, resposta do recebedor) ----------
  const conectarWs = useCallback(() => {
    const filtro = motoristaId != null ? `motorista_id=${motoristaId}` : `rota_id=${rotaId}`;
    const url = `${base.replace(/^http/, "ws")}/ws?${filtro}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onmessage = (m) => {
      const { canal, dado } = JSON.parse(String(m.data)) as {
        [K in keyof MensagensStream]: { canal: K; dado: MensagensStream[K] };
      }[keyof MensagensStream];
      switch (canal) {
        case "snapshot":
          setEventos(dado.eventos.slice(0, maxEventos));
          setTask(dado.tasks[0] ?? null);
          setEstadia(dado.estadias.find((e) => !e.encerrada) ?? dado.estadias[0] ?? null);
          setLigacao(dado.ligacoes[0] ?? null);
          break;
        case "evento":
          setEventos((xs) => [dado, ...xs].slice(0, maxEventos));
          if (dado.tipo === "rota_atribuida" && dado.rota_id != null) onRotaAtribuida?.(dado.rota_id);
          if (dado.tipo === "resposta_recebedor") {
            const d = dado.dados as { ligacao_id?: number; previsao?: string; doca?: string; motivo?: string };
            setLigacao((l) => ({
              ...(l ?? ({} as Ligacao)),
              id: d.ligacao_id ?? l?.id ?? 0,
              status: "respondida",
              atendida: true,
              previsao: d.previsao ?? null,
              doca: d.doca ?? null,
              motivo_espera: d.motivo ?? null,
              resposta_resumo: dado.mensagem,
            }));
          }
          break;
        case "task":
          setTask(dado.task);
          break;
        case "contador":
          setEstadia((atual) => dado.estadias[0] ?? (atual && { ...atual }));
          break;
        case "fala":
          if (dado.papel === "motorista") setFalas((xs) => [{ texto: dado.texto, em: Date.now() }, ...xs].slice(0, 20));
          break;
        case "reset":
          setEventos([]); setTask(null); setEstadia(null); setLigacao(null); setFalas([]);
          break;
      }
    };
    ws.onclose = () => {
      wsRef.current = null;
      if (vivoRef.current) setTimeout(conectarWs, 2000); // reconecta
    };
  }, [base, rotaId, motoristaId, onRotaAtribuida, maxEventos]);

  useEffect(() => {
    vivoRef.current = true;
    conectarWs();
    return () => {
      vivoRef.current = false;
      wsRef.current?.close();
    };
  }, [conectarWs]);

  // ---------- Sala LiveKit ----------
  const iniciar = useCallback(async () => {
    setErro(null);
    setStatus("conectando");
    try {
      if (!(await pedirMicrofone())) throw new Error("permissão de microfone negada");
      const s = await json<Sessao>(
        await fetch(`${base}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rota_id: rotaId }),
        }),
      );
      if (!s.livekit_url || !s.token || !s.identity) throw new Error("backend sem credenciais do LiveKit");
      sessaoRef.current = s;
      setSessao(s);
      await AudioSession.startAudioSession();
      const room = new Room();
      roomRef.current = room;
      room.on(RoomEvent.ParticipantConnected, (participant) => {
        if (participant.identity === `rodar-agente-${s.id}`) setStatus("conversando");
      });
      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        if (participant.identity === `rodar-agente-${s.id}`) setStatus("aguardando_agente");
      });
      room.on(RoomEvent.Disconnected, () => setStatus("parado"));
      await room.connect(s.livekit_url, s.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setStatus(room.remoteParticipants.has(`rodar-agente-${s.id}`) ? "conversando" : "aguardando_agente");
    } catch (e) {
      setErro(String(e));
      setStatus("erro");
    }
  }, [base, rotaId]);

  const encerrar = useCallback(async () => {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    await AudioSession.stopAudioSession();
    const s = sessaoRef.current;
    sessaoRef.current = null;
    setSessao(null);
    setStatus("parado");
    if (s) await fetch(`${base}/sessions/${s.id}`, { method: "DELETE" }).catch(() => undefined);
  }, [base]);

  const alternarMudo = useCallback(() => {
    setMudo((m) => {
      roomRef.current?.localParticipant.setMicrophoneEnabled(!m).catch(() => undefined);
      return !m;
    });
  }, []);

  /** GPS real do celular (opcional; na demo quem manda a posição é o simulador). */
  const enviarPosicao = useCallback(
    async (lat: number, lng: number, velocidadeKmh?: number, precisaoM?: number) => {
      await fetch(`${base}/rotas/${rotaId}/posicao`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lng, velocidade_kmh: velocidadeKmh, precisao_m: precisaoM }),
      });
    },
    [base, rotaId],
  );

  // Libera o motor ao desmontar.
  useEffect(
    () => () => {
      const room = roomRef.current;
      if (!room) return;
      room.disconnect();
      roomRef.current = null;
      AudioSession.stopAudioSession();
      const s = sessaoRef.current;
      if (s) fetch(`${base}/sessions/${s.id}`, { method: "DELETE" }).catch(() => undefined);
    },
    [base],
  );

  return {
    status, erro, sessao, mudo,
    eventos, falas, estadia, task, ligacao,
    iniciar, encerrar, alternarMudo, enviarPosicao,
  };
}
