/**
 * Hook React para o painel do CCO (Vite + React). Mantém o estado vivo a partir do SSE.
 *
 *   const cco = useAvisaiCCO(import.meta.env.VITE_AVISAI_API);
 *   cco.tasks.map(t => <Task key={t.id} t={t} onAssumir={() => cco.confirmarTask(t.id, "Ana")} />)
 *   cco.estadias[0]?.valor_fmt
 */
import { useEffect, useMemo, useState } from "react";

import type { Estadia, EventoStream, Ligacao, Rota, Snapshot, TaskCCO } from "../tipos";
import { AvisaiStream, type StatusConexao } from "./avisaiStream";

function upsert<T extends { id: number }>(xs: T[], x: T): T[] {
  const i = xs.findIndex((y) => y.id === x.id);
  if (i < 0) return [x, ...xs];
  const c = xs.slice();
  c[i] = x;
  return c;
}

/** O contador traz só as estadias abertas: atualiza essas e mantém as encerradas. */
function mesclarEstadias(atuais: Estadia[], abertas: Estadia[]): Estadia[] {
  const novas = new Map(abertas.map((e) => [e.estadia_id, e]));
  const fora = abertas.filter((e) => !atuais.some((a) => a.estadia_id === e.estadia_id));
  return [...fora, ...atuais.map((a) => novas.get(a.estadia_id) ?? a)];
}

export function useAvisaiCCO(api: string, rotaId?: number, maxEventos = 100) {
  const cliente = useMemo(() => new AvisaiStream(api, rotaId), [api, rotaId]);
  const [conexao, setConexao] = useState<StatusConexao>("desconectado");
  const [rotas, setRotas] = useState<Rota[]>([]);
  const [tasks, setTasks] = useState<TaskCCO[]>([]);
  const [estadias, setEstadias] = useState<Estadia[]>([]);
  const [ligacoes, setLigacoes] = useState<Ligacao[]>([]);
  const [eventos, setEventos] = useState<EventoStream[]>([]);
  const [falas, setFalas] = useState<{ rota_id: number; papel: string; texto: string; em: number }[]>([]);

  useEffect(() => {
    const aplicar = (s: Snapshot) => {
      setRotas(s.rotas);
      setTasks(s.tasks);
      setEstadias(s.estadias);
      setLigacoes(s.ligacoes);
      setEventos(s.eventos.slice(0, maxEventos));
    };
    cliente.onStatus = setConexao;
    const off = [
      cliente.on("snapshot", aplicar),
      cliente.on("evento", (e) => {
        setEventos((xs) => [e, ...xs].slice(0, maxEventos));
        // ligações mudam por evento: recarrega o snapshot quando for o caso
        if (e.tipo.startsWith("ligacao") || e.tipo === "resposta_recebedor" || e.tipo === "fallback_plano_b") {
          cliente.estado().then((s) => setLigacoes(s.ligacoes)).catch(() => undefined);
        }
      }),
      cliente.on("task", ({ task }) => setTasks((xs) => upsert(xs, task))),
      cliente.on("contador", ({ estadias: abertas }) => setEstadias((xs) => mesclarEstadias(xs, abertas))),
      cliente.on("posicao", (p) =>
        setRotas((xs) => xs.map((r) => (r.id === p.rota_id ? { ...r, ultima_lat: p.lat, ultima_lng: p.lng, distancia_m: p.distancia_m, eta_min: p.eta_min, status: p.status } : r)))),
      cliente.on("fala", (f) => setFalas((xs) => [{ ...f, em: Date.now() }, ...xs].slice(0, 50))),
      cliente.on("reset", () => cliente.estado().then(aplicar).catch(() => undefined)),
    ];
    cliente.conectar();
    return () => {
      off.forEach((f) => f());
      cliente.fechar();
    };
  }, [cliente, maxEventos]);

  return {
    conexao, rotas, tasks, estadias, ligacoes, eventos, falas,
    confirmarTask: (id: number, por?: string) => cliente.confirmarTask(id, por),
    confirmarDescarga: (rid: number, por?: string) => cliente.confirmarDescarga(rid, por),
    ligarRecebedor: (rid: number) => cliente.ligarRecebedor(rid),
    resetDemo: (rid: number) => cliente.resetDemo(rid),
    cliente,
  };
}
