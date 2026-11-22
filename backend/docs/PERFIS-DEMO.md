# Perfis persistidos da demonstração

`GET /usuarios` e `GET /api/users` retornam o mesmo array de perfis. O filtro
opcional `?role=cco` ou `?role=driver` restringe o papel; outro valor recebe 422.
A ordenação é por papel, nome e identificador.

```json
{
  "id": "1",
  "email": "carlos@rotasul.test",
  "name": "Carlos Andrade",
  "role": "driver",
  "driverId": 1,
  "tripId": "1"
}
```

O DTO é exatamente `POST /auth/sso` → `user`. `id` é a chave primária de
`Usuario` serializada como string; os números do exemplo não são constantes.
`driverId` é número ou `null`; `tripId` é string ou `null`, calculado pela viagem
mais recente atribuída e ainda não descarregada. Para CCO ambos são `null`.
O nome do motorista vem sempre de `Motorista.nome`; CCO usa `Usuario.nome`.

## Login e cadastro

O login continua MOCK: o e-mail conhecido seleciona um perfil e recebe token
fictício. Não há senha, assinatura, autenticação ou autorização real. E-mail
desconhecido recebe 404; não há fallback para outro motorista nem inferência de
CCO pelo texto do e-mail. Sem e-mail, mantém-se `carlos@rotasul.test`.
E-mails são normalizados com trim e letras minúsculas.

`POST /motoristas` com e-mail válido cria motorista e perfil na mesma transação.
E-mail já cadastrado, inclusive de CCO, recebe 409 sem modificar o cadastro.
Sem e-mail, cria apenas motorista, que não aparece no seletor de perfis.

## População idempotente

Execute `alembic upgrade head` e `python -m app.seed`. A migração acrescenta
`usuario` e vincula motoristas preexistentes com e-mail válido e único. O seed
complementa os registros ausentes:

| E-mail | Nome inicial | Papel | Viagem inicial |
| --- | --- | --- | --- |
| cco@avisai.test | Ana (CCO) | cco | nenhuma |
| cco.turno2@avisai.test | Bruno (CCO) | cco | nenhuma |
| carlos@rotasul.test | Carlos Andrade | driver | rota histórica, quando a base está vazia |
| marina@rotasul.test | Marina Souza | driver | NF `DEMO-AVISAI-002` |
| joao@rotasul.test | João Pereira | driver | NF `DEMO-AVISAI-003` |
| fernanda@rotasul.test | Fernanda Lima | driver | nenhuma |

Em base vazia são 6 perfis, 4 motoristas e 3 rotas. Bases existentes podem ter
mais registros. Marina, João e Fernanda têm telefone `null`; novos recebedores são
explicitamente fictícios e têm telefone vazio. Não há chamadas externas.

Identidade é preservada por e-mail; viagens adicionais são reconhecidas pela NF
exclusiva, mesmo depois de descarregadas ou reatribuídas. Rodar o seed novamente
não renomeia pessoas, não troca atribuições, não reabre viagens e não cria uma
substituta para viagem concluída. A rota histórica só é criada se não há rota
alguma. Duplicatas legadas de e-mail permanecem intocadas e não recebem uma
seleção arbitrária de perfil. Um motorista que já tem qualquer viagem atribuída,
inclusive concluída, não recebe nova viagem da população.

Existe um backfill intencional e restrito: Carlos sem e-mail só é reutilizado
quando coincide com o fixture histórico completo (nome e telefone de seed,
empresa de seed e rota com placa `RST-4B21`/NF `000.482.913`). Nesse caso, apenas
o e-mail conhecido é preenchido; o ID e a atribuição original permanecem.
Cadastros parecidos fora desse predicado não são mesclados.

O comando imprime contagens agregadas. Não use `--reset` para atualizar uma base
existente: essa opção destrutiva anterior continua disponível apenas para
recriar explicitamente a demo. O seed normal não remove eventos, anexos ou dados
operacionais.
