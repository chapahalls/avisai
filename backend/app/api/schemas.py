"""Contrato com o front (aparece no /openapi.json; gere tipos com openapi-typescript)."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TokenOut(BaseModel):
    url: str
    room: str
    identity: str
    token: str


class NovaSessao(BaseModel):
    rota_id: int = 1


class SessaoOut(BaseModel):
    id: int
    rota_id: int
    papel: str
    canal: str
    agent_id: Optional[str]
    status: str
    llm_mode: str
    criada_em: datetime
    encerrada_em: Optional[datetime] = None
    erro: Optional[str] = None
    livekit_url: Optional[str] = None
    identity: Optional[str] = None
    token: Optional[str] = None


class Fala(BaseModel):
    texto: str
    prioridade: str = "APPEND"


class Posicao(BaseModel):
    lat: float
    lng: float
    velocidade_kmh: Optional[float] = None
    precisao_m: Optional[float] = None
    fonte: str = "celular"  # celular (GPS do app) | rastreador (GPS do caminhão)


class NovaSolicitacao(BaseModel):
    pergunta: str


class NovaMensagemMotorista(BaseModel):
    remetente: str = Field(min_length=1, max_length=255)
    texto: str = Field(min_length=1, max_length=2000)


class ResponderChamado(BaseModel):
    resposta: str = Field(min_length=1, max_length=2000)
    respondido_por: str = "CCO"


class PosicaoOut(BaseModel):
    rota_id: int
    distancia_m: float
    eta_min: float
    status: str
    disparos: list[str]


class Confirmar(BaseModel):
    confirmado_por: str = "CCO"


class Descarga(BaseModel):
    por: str = "CCO"


class Ligar(BaseModel):
    motivo: str = "cco_sem_resposta"


class LigarAgente(BaseModel):
    destino: Literal["operador", "supervisor", "motorista"] = "operador"
    motivo: str = Field(min_length=1, max_length=1000)


class EventoStream(BaseModel):
    """Envelope dos eventos no SSE (/cco/stream, evento `evento`) e no WS (/ws)."""
    id: int
    tipo: str
    rota_id: Optional[int]
    timestamp: datetime
    mensagem: str
    dados: dict[str, Any]


class DomainEventIn(BaseModel):
    """Evento do outbox do app (docs/arquitetura-avisai.md, seção 7)."""
    id: Optional[str] = None
    idempotencyKey: str
    tripId: str
    type: str
    occurredAt: Optional[str] = None
    source: str = "driver"
    payload: dict[str, Any] = {}


E164 = r"^\+[1-9]\d{7,14}$"


class VinculoGeo(BaseModel):
    """De onde veio a coordenada: resultado escolhido na geocodificação ou digitada pelo CCO."""
    fonte: Literal["geocodificacao", "manual"]
    provedor: Optional[str] = Field(default=None, max_length=40)
    id: Optional[str] = Field(default=None, max_length=120)  # identificador do lugar no provedor
    endereco: Optional[str] = Field(default=None, max_length=500)  # endereço como o provedor devolveu

    @model_validator(mode="after")
    def _geocodificacao_identificada(self):
        if self.fonte == "geocodificacao" and not (self.provedor and self.id):
            raise ValueError("geocodificação exige provedor e id do lugar")
        return self


class Ponto(BaseModel):
    nome: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    endereco: str = Field(default="", max_length=300)
    geo: Optional[VinculoGeo] = None


class GeoResultado(BaseModel):
    id: str
    endereco: str
    lat: float
    lng: float
    tipo: Optional[str] = None


class GeocodificacaoOut(BaseModel):
    provedor: str
    atribuicao: str
    resultados: list[GeoResultado]


class Cancelar(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)
    por: str = Field(default="CCO", min_length=1, max_length=80)


class RecebedorIn(BaseModel):
    empresa: str
    nome: str
    telefone_e164: str = Field(pattern=E164)


class NovaRota(BaseModel):
    """Rota publicada pela transportadora no CCO. motorista_id opcional (atribui na hora)."""
    origem: Ponto
    destino: Ponto
    recebedor: RecebedorIn
    carga_descricao: str = ""
    carga_t: float = Field(gt=0)
    capacidade_t: Optional[float] = Field(default=None, gt=0, description="Capacidade total do veículo (t); base da estadia. Vazio = carga_t.")
    placa: str = ""
    nota_fiscal: str = ""
    janela_descarga: str = ""
    empresa_id: int = 1
    motorista_id: Optional[int] = None

    @model_validator(mode="after")
    def _capacidade_cobre_a_carga(self):
        if self.capacidade_t is not None and self.capacidade_t < self.carga_t:
            raise ValueError("capacidade_t não pode ser menor que carga_t")
        return self


class Atribuir(BaseModel):
    motorista_id: int


class NovoMotorista(BaseModel):
    nome: str
    telefone_e164: Optional[str] = Field(default=None, pattern=E164)
    email: Optional[str] = None
    empresa_id: int = 1


class NovoOperador(BaseModel):
    nome: str
    email: str


CategoriaArquivo = Literal["documento", "nota_fiscal", "comprovante", "imagem", "outro"]


class ArquivoRotaOut(BaseModel):
    id: int
    rota_id: int
    nome_original: str
    tipo_mime: str
    tamanho_bytes: int
    categoria: CategoriaArquivo
    descricao: Optional[str]
    criado_em: datetime
    url_download: str



class PerfilUsuarioOut(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["cco", "driver"]
    driverId: Optional[int]
    tripId: Optional[str]


class SsoOut(BaseModel):
    token: str
    user: PerfilUsuarioOut


LayoutEdi = Literal["ocoren-5.0", "ocoren-3.1"]


class ParceiroEdiIn(BaseModel):
    """Perfil de parceiro de EDI: escolhe o layout e o De-Para, nunca muda código (conectores/edi)."""
    empresa_id: int = 1
    nome: str = Field(min_length=1, max_length=120)
    layout: LayoutEdi = "ocoren-5.0"
    caixa_remetente: str = Field(default="", max_length=120)
    caixa_destinatario: str = Field(default="", max_length=120)
    depara: dict[str, str] = {}
    campos_extras: dict[str, Any] = {}
    codificacao: str = "cp1252"
    fim_de_linha: str = "\r\n"
    transporte: Literal["download"] = "download"  # até 30/11: sem SFTP/fila (ver docs/edi/ocoren-integracao.md)


class ParceiroEdiPatch(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=120)
    layout: Optional[LayoutEdi] = None
    caixa_remetente: Optional[str] = Field(default=None, max_length=120)
    caixa_destinatario: Optional[str] = Field(default=None, max_length=120)
    depara: Optional[dict[str, str]] = None
    campos_extras: Optional[dict[str, Any]] = None
    codificacao: Optional[str] = None
    fim_de_linha: Optional[str] = None


class ParceiroEdiOut(BaseModel):
    id: int
    empresa_id: int
    nome: str
    layout: str
    caixa_remetente: str
    caixa_destinatario: str
    depara: dict[str, str]
    campos_extras: dict[str, Any]
    codificacao: str
    fim_de_linha: str
    transporte: str
    criado_em: datetime


class ErroValidacaoEdi(BaseModel):
    linha: int
    registro: Optional[str] = None
    campo: Optional[str] = None
    erro: str


class RegistroValidadoEdi(BaseModel):
    linha: int
    registro: str
    valores: dict[str, Optional[str]]


class ValidacaoEdiOut(BaseModel):
    ok: bool
    erros: list[ErroValidacaoEdi]
    registros: list[RegistroValidadoEdi]
