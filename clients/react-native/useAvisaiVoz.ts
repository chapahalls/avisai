/**
 * Hook do app do motorista (React Native): conversa por voz com o agente AvisAI.
 *
 * Copie `clients/tipos.ts` e este arquivo para o app.
 * Dependência: `react-native-agora` >= 4.5.1 (testado com as tipagens da 4.6.4). Tem módulo nativo:
 * precisa de dev build ou `expo prebuild` (não roda no Expo Go).
 * Permissões: Android RECORD_AUDIO (pedida aqui), iOS NSMicrophoneUsageDescription no Info.plist.
 *
 *   const voz = useAvisaiVoz({ api: "https://xxxx.trycloudflare.com", rotaId: 1 });
 *   <Button title="Falar com o AvisAI" onPress={voz.iniciar} />
 *   <Text>{voz.status} · {voz.estadia?.tempo_parado} · {voz.estadia?.valor_fmt}</Text>
 *
 * Só controle e mídia: o áudio vai do celular direto para a Agora; o backend só cria o agente.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { PermissionsAndroid, Platform } from "react-native";
import createAgoraRtcEngine, {
  AudioRoute,
  AudioScenarioType,
  ChannelProfileType,
  ClientRoleType,
  type IRtcEngine,
  type IRtcEngineEventHandler,
} from "react-native-agora";

import type { EventoStream, Estadia, Ligacao, MensagensStream, Sessao, TaskCCO } from "../tipos";

export type StatusVoz =
  | "parado" // sem sessão
  | "conectando" // criando o agente / entrando no canal
  | "aguardando_agente" // no canal, esperando o agente (uid 9001) entrar
  | "conversando" // agente no canal: pode falar (e interromper)
  | "erro";

export interface FalaAgente {
  texto: string;
  em: number;
}

export interface OpcoesVoz {
  api: string; // URL pública do backend (PUBLIC_URL do túnel)
  rotaId: number;
  /** Quantos eventos manter em memória (padrão 50). */
  maxEventos?: number;
}

/** Parâmetros de áudio recomendados pela Agora para agentes de voz (/en/ai/best-practices/audio-setup). */
function aplicarAudioIA(engine: IRtcEngine, rota: number) {
  const p = (o: Record<string, unknown>) => engine.setParameters(JSON.stringify(o));
  p({ "che.audio.aec.split_srate_for_48k": 16000 });
  p({ "che.audio.sf.enabled": true });
  p({ "che.audio.sf.stftType": 6 });
  p({ "che.audio.sf.ainlpLowLatencyFlag": 1 });
  p({ "che.audio.sf.ainsLowLatencyFlag": 1 });
  p({ "che.audio.sf.procChainMode": 1 });
  p({ "che.audio.sf.nlpDynamicMode": 1 });
  const fone = [
    AudioRoute.RouteHeadset,
    AudioRoute.RouteEarpiece,
    AudioRoute.RouteHeadsetnomic,
    AudioRoute.RouteBluetoothDeviceHfp,
    AudioRoute.RouteBluetoothDeviceA2dp,
  ].includes(rota);
  p({ "che.audio.sf.nlpAlgRoute": fone ? 0 : 1 });
  p({ "che.audio.sf.ainlpModelPref": 10 });
  p({ "che.audio.sf.nsngAlgRoute": 12 });
  p({ "che.audio.sf.ainsModelPref": 10 });
  p({ "che.audio.sf.nsngPredefAgg": 11 });
  p({ "che.audio.agc.enable": false });
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

export function useAvisaiVoz({ api, rotaId, maxEventos = 50 }: OpcoesVoz) {
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

  const engineRef = useRef<IRtcEngine | null>(null);
  const handlerRef = useRef<IRtcEngineEventHandler | null>(null);
  const sessaoRef = useRef<Sessao | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const vivoRef = useRef(true);

  // ---------- WebSocket com eventos da rota (legenda, contador, Task, resposta do recebedor) ----------
  const conectarWs = useCallback(() => {
    const url = `${base.replace(/^http/, "ws")}/ws?rota_id=${rotaId}`;
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
  }, [base, rotaId, maxEventos]);

  useEffect(() => {
    vivoRef.current = true;
    conectarWs();
    return () => {
      vivoRef.current = false;
      wsRef.current?.close();
    };
  }, [conectarWs]);

  // ---------- Motor RTC ----------
  const obterEngine = useCallback((appId: string): IRtcEngine => {
    if (engineRef.current) return engineRef.current;
    const engine = createAgoraRtcEngine();
    engine.initialize({
      appId,
      channelProfile: ChannelProfileType.ChannelProfileLiveBroadcasting,
      audioScenario: AudioScenarioType.AudioScenarioAiClient, // cenário da Agora para agentes de IA
    });
    engine.enableAudio();
    aplicarAudioIA(engine, AudioRoute.RouteDefault);
    const handler: IRtcEngineEventHandler = {
      onUserJoined: (_c, uid) => {
        if (uid === sessaoRef.current?.agent_uid) setStatus("conversando");
      },
      onUserOffline: (_c, uid) => {
        if (uid === sessaoRef.current?.agent_uid) setStatus("aguardando_agente");
      },
      onTokenPrivilegeWillExpire: async () => {
        const s = sessaoRef.current;
        if (!s) return;
        try {
          const t = await json<{ token: string }>(await fetch(`${base}/token?channel=${s.canal}&uid=${s.user_uid}`));
          engineRef.current?.renewToken(t.token);
        } catch (e) {
          setErro(`falha ao renovar token: ${String(e)}`);
        }
      },
      onAudioRoutingChanged: (rota) => engineRef.current && aplicarAudioIA(engineRef.current, rota),
      onError: (err, msg) => setErro(`Agora ${err}: ${msg}`),
    };
    engine.registerEventHandler(handler);
    engineRef.current = engine;
    handlerRef.current = handler;
    return engine;
  }, [base]);

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
      if (!s.app_id || !s.token) throw new Error("backend sem credenciais da Agora");
      sessaoRef.current = s;
      setSessao(s);
      const engine = obterEngine(s.app_id);
      engine.setEnableSpeakerphone(true); // viva-voz na cabine
      engine.joinChannel(s.token, s.canal, s.user_uid, {
        clientRoleType: ClientRoleType.ClientRoleBroadcaster,
        publishMicrophoneTrack: true,
        publishCameraTrack: false,
        autoSubscribeAudio: true,
        autoSubscribeVideo: false,
      });
      // O 200 do /sessions não quer dizer que o agente já entrou: esperamos onUserJoined(9001).
      setStatus("aguardando_agente");
    } catch (e) {
      setErro(String(e));
      setStatus("erro");
    }
  }, [base, rotaId, obterEngine]);

  const encerrar = useCallback(async () => {
    engineRef.current?.leaveChannel();
    const s = sessaoRef.current;
    sessaoRef.current = null;
    setSessao(null);
    setStatus("parado");
    if (s) await fetch(`${base}/sessions/${s.id}`, { method: "DELETE" }).catch(() => undefined);
  }, [base]);

  const alternarMudo = useCallback(() => {
    setMudo((m) => {
      engineRef.current?.muteLocalAudioStream(!m);
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
      const e = engineRef.current;
      if (!e) return;
      e.leaveChannel();
      if (handlerRef.current) e.unregisterEventHandler(handlerRef.current);
      e.release();
      engineRef.current = null;
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
