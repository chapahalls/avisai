# Anexos reais por viagem

O CCO pode anexar um arquivo ao registro numérico da rota; o app móvel lista e baixa o mesmo conteúdo.
Os documentos de `/api/documents` continuam fictícios, com `mock:true` e `fileUri:null`. Anexar
um PDF não valida documento fiscal, não extrai seus campos e não transforma os dados mock em dados reais.

## Contrato

- `GET /rotas/{rota_id}/arquivos`: array de metadados, ID decrescente; vazio é `[]`.
- `POST /rotas/{rota_id}/arquivos`: `multipart/form-data`, campo **arquivo** obrigatório;
  **categoria** opcional (`documento`, `nota_fiscal`, `comprovante`, `imagem`, `outro`, padrão `documento`);
  **descricao** opcional (até 1.000 caracteres). HTTP **201**, com os metadados do arquivo salvo.
- `GET /rotas/{rota_id}/arquivos/{arquivo_id}/download`: bytes originais, `Content-Type` validado,
  `Content-Disposition: attachment` com nome sanitizado, `X-Content-Type-Options: nosniff`
  e `Cache-Control: private, no-store`.

```json
{
  "id": 1,
  "rota_id": 42,
  "nome_original": "nota.pdf",
  "tipo_mime": "application/pdf",
  "tamanho_bytes": 12000,
  "categoria": "nota_fiscal",
  "descricao": null,
  "criado_em": "2026-11-22T13:00:00Z",
  "url_download": "/rotas/42/arquivos/1/download"
}
```

IDs são inteiros estáveis e a URL é relativa à raiz da API configurada. O cliente deve construir
o download com a URL de backend confiável e esses IDs; não aceitar `fileUri`, caminhos ou hosts
arbitrários. As respostas nunca expõem a chave de armazenamento. Não existe `createdBy` porque
o backend não tem identidade autenticada para atribuir autoria.

Aceita PDF, JPEG/JPG, PNG, WebP e GIF. Extensão, assinatura inicial e MIME informado devem ser
compatíveis; `application/octet-stream` é aceito para clientes móveis, mantendo o MIME detectado.
Não aceita HTML/SVG, arquivos vazios ou assinatura incompatível. Essa verificação não é antivírus,
leitor fiscal ou garantia de que um documento/imagem está estruturalmente completo.

Erros: **413** acima do limite; **415** formato inválido; **422** campos inválidos;
**404** rota, arquivo, conteúdo ausente ou arquivo de outra rota.

## Mobile e eventos

Após o commit do arquivo e do evento na mesma transação, SSE e WS publicam:

```json
{
  "id": 15,
  "tipo": "arquivo_adicionado",
  "rota_id": 42,
  "timestamp": "2026-11-22T13:00:00Z",
  "mensagem": "Arquivo anexado: nota.pdf",
  "dados": {
    "arquivo_id": 1,
    "nome_original": "nota.pdf",
    "categoria": "nota_fiscal",
    "tipo_mime": "application/pdf",
    "tamanho_bytes": 12000
  }
}
```

O canal é `evento`; no WS o envelope é `{canal:"evento",dado:<evento>}`.
O cliente filtra `rota_id`, refaz a listagem e exibe disponibilidade; não afirma que o arquivo
foi recebido, aberto ou lido. `GET /events` mapeia esse evento para `TripFileAdded`, `source:"cco"`.
SSE/WS não oferecem replay; listar arquivos após conectar/reconectar recupera anexos perdidos.

O filtro de motorista no WS inicia vazio quando não há rota atribuída, atualiza o contador
para a rota atual e deixa de publicar viagens reatribuídas a outro motorista. Isso organiza
o stream; não fornece autenticação nem autorização.

## Persistência e configuração

`ARQUIVOS_MAX_BYTES` define o tamanho máximo de um arquivo (padrão **10485760**, 10 MiB;
intervalo aceito 1 a 104857600 bytes). O limite do corpo multipart é esse valor + 64 KiB para
cabeçalhos/campos e também vale sem Content-Length. O corpo é verificado em spool antes de
o parser multipart processá-lo; cada arquivo tem seu próprio limite durante a gravação.

`ARQUIVOS_DIR` define uma raiz local administrada pelo servidor; padrão `data/arquivos`
relativo ao cwd do backend, `/app/data/arquivos` em Docker. O compose monta explicitamente
`./backend/data/arquivos:/app/data/arquivos`; a pasta existe no checkout e seu conteúdo é
ignorado pelo Git. Deve permanecer gravável pelo UID/GID configurado para o container.

A migração `b643fd18c299` cria a tabela `arquivo_rota` (FK da rota e chave de storage única).
O conteúdo usa nomes UUID internos e não o nome enviado pelo cliente. Nenhum upload sobrescreve
outro. O download valida a raiz e rejeita chaves adulteradas e symlinks.

Reset operacional preserva metadados e conteúdo. Não há DELETE de anexos nesta entrega.
Faça backup do banco e do volume juntos. Em falhas normais, arquivos parciais e conteúdo sem
commit são removidos; um processo morto entre gravação e commit pode deixar arquivo órfão,
que não aparece na API. Remover órfãos exige confrontar as chaves com o banco durante manutenção.
Downgrade da tabela não apaga o volume e deve ser acompanhado de backup.

O SSO é mock, sem senha. Com `AUTH_OBRIGATORIA=true` (padrão), listar e baixar exigem um JWT da
central ou do motorista atribuído à rota; anexar exige um JWT da central. Com `false`, os
endpoints ficam sem autorização e devem ser usados apenas em desenvolvimento local. IDs não são
controle de acesso.

## Verificação

`make test ARGS="tests/api/test_arquivos.py tests/api/test_publicacao_rota.py"` usa o banco
isolado `avisai_test`, diretórios temporários e fakes; não chamam serviços de voz. Os cenários cobrem
upload/lista/download, formatos, nomes com traversal, chaves/symlinks adulterados, limites,
multipart sem Content-Length, duplicidade de nomes, 404, reset e entrega pelo stream móvel.
