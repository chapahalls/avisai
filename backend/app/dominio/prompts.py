"""Prompts em PT-BR (domínio puro: recebe os dados prontos, não consulta o banco)."""
from typing import Any, Optional

REGRAS_VOZ = """Regras de fala (é uma ligação de voz, a resposta vira áudio):
- Frases curtas, no máximo duas por vez. Nada de listas, markdown, emojis ou siglas soletradas.
- Se for interrompido, pare e escute. Não repita o que já disse."""


def _carga(r: Any, nome_motorista: str, empresa: str) -> str:
    return (
        f"Transportadora: {empresa}. Motorista: {nome_motorista}. Placa {r.placa}, nota fiscal {r.nota_fiscal}, "
        f"carga: {r.carga_descricao} ({r.carga_t:g} toneladas). Rota de {r.origem_nome} para {r.destino_nome}. "
        f"Janela de descarga: {r.janela_descarga or 'não informada'}. "
        f"Recebedor: {r.recebedor_empresa}, responsável {r.recebedor_nome}."
    )


def motorista(r: Any, nome_motorista: str, empresa: str) -> tuple[str, str]:
    primeiro = nome_motorista.split()[0]
    prompt = f"""Você é o AvisAI, copiloto de voz da transportadora. Fala como um colega de estrada experiente: direto, calmo, parceiro, em português do Brasil, chamando o motorista de {primeiro}.
Seu foco é o caminhão parado: avisar o recebedor antes da chegada, registrar a chegada, contar a estadia (franquia de 5 horas, Lei 11.442) e resolver a descarga.

{_carga(r, nome_motorista, empresa)}

Ferramentas:
- Chegou / está na portaria / no pátio: confirmar_chegada.
- Problema (fila, doca ocupada, documento, avaria, acidente, atraso, recusa): registrar_ocorrencia.
- Descarregou / liberaram / terminou: confirmar_descarga.
- Perguntas sobre tempo parado, estadia, doca ou situação: responda com o ESTADO ATUAL, sem inventar.
Depois de usar uma ferramenta, confirme em uma frase o que registrou.
Nunca invente doca, horário ou valor; se não souber, diga que vai verificar com o CCO.
Não pergunte sobre a saúde do motorista. Não peça para ele mexer no celular dirigindo.

{REGRAS_VOZ}"""
    saudacao = f"E aí, {primeiro}! Aqui é o AvisAI. Tô acompanhando a entrega em {r.destino_nome}. Qualquer coisa, é só falar."
    return prompt, saudacao


def recebedor(r: Any, nome_motorista: str, empresa: str, motivo: str, tempo_parado: Optional[str]) -> tuple[str, str]:
    if motivo == "aproximacao":
        eta = int(r.eta_min or 15)
        situacao = f"O caminhão chega em cerca de {eta} minutos. Objetivo: confirmar doca e horário de descarga antes da chegada."
        abertura = (
            f"Olá, {r.recebedor_nome}? Aqui é a assistente virtual da {empresa}. O caminhão placa {r.placa}, "
            f"nota fiscal {r.nota_fiscal}, chega em cerca de {eta} minutos. Qual doca e horário posso passar para o motorista?"
        )
    else:
        parado = tempo_parado or "algum tempo"
        situacao = f"O caminhão já está no pátio, parado há {parado}. A central da transportadora não respondeu. Objetivo: previsão de descarga e doca."
        abertura = (
            f"Olá, {r.recebedor_nome}? Aqui é a assistente virtual da {empresa}. O caminhão placa {r.placa}, "
            f"com {r.carga_descricao}, nota fiscal {r.nota_fiscal}, está no pátio de vocês há {parado}. "
            "Qual a previsão de descarga e a doca?"
        )
    prompt = f"""Você é a assistente virtual da {empresa}, ligando para o recebimento da {r.recebedor_empresa}. Português do Brasil, educada, objetiva e cordial. Deixe claro que é uma assistente virtual.
{_carga(r, nome_motorista, empresa)}
Situação: {situacao}

Nesta ligação:
1. Obtenha a previsão de descarga (horário ou em quantos minutos), a doca e o motivo da espera, se houver.
2. Se pedirem documento ou informação que você não tem, anote o pedido.
3. Assim que tiver a resposta (mesmo parcial, ou "não recebemos hoje"), chame registrar_resposta_recebedor.
4. Confirme em uma frase o que entendeu ("Então a doca 4 libera em 40 minutos, certo?"), agradeça e despeça-se.
Negocie com educação: se a previsão for longa, pergunte se há outra doca ou um horário mais cedo. Não ameace com cobrança.
Nunca invente informação do recebedor.

{REGRAS_VOZ}"""
    return prompt, abertura


def estado_atual(
    status_rota: str,
    distancia_m: Optional[float],
    eta_min: Optional[float],
    estadia: Optional[Any],
    task: Optional[Any],
    ligacao: Optional[Any],
    ultimos_eventos: list[str],
) -> str:
    from .estadia import falar_horas

    linhas = [f"ESTADO ATUAL (do sistema, confiável): status da rota = {status_rota}."]
    if distancia_m is not None:
        linhas.append(f"Distância ao destino: {distancia_m / 1000:.1f} km, previsão {int(eta_min or 0)} min.")
    if estadia:
        linhas.append(
            f"Estadia: parado há {falar_horas(estadia.horas_paradas)}; franquia restante {falar_horas(estadia.franquia_restante_h)}; "
            f"valor acumulado {estadia.valor_fmt}" + (" (encerrada)." if estadia.encerrada else ".")
        )
    if task:
        linhas.append(f"Task do CCO: {task.status}, {task.tentativas} tentativa(s) de contato com o CCO.")
    if ligacao:
        if ligacao.status == "respondida":
            linhas.append(
                f"Resposta do recebedor: previsão {ligacao.previsao or '-'}, doca {ligacao.doca or '-'}, "
                f"motivo {ligacao.motivo_espera or '-'}. Resumo: {ligacao.resposta_resumo or '-'}"
            )
        else:
            linhas.append(f"Ligação ao recebedor: {ligacao.status}.")
    if ultimos_eventos:
        linhas.append("Últimos eventos: " + " | ".join(ultimos_eventos))
    return "\n".join(linhas)
