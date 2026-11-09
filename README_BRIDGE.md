# NEXO · Ponte de persistência para o Google Meu Drive

Código de transporte e testes **sem dados de pesquisa, chaves ou IDs privados**. O código-fonte público permanece no `Nexo-test`, mas a execução com acesso a informações privadas deve acontecer exclusivamente num repositório/runner privado, a partir de commit fixado. O fluxo **não** aceita código ou comandos vindos da Tower.

## Estados

* `TECH_SMOKE`: apenas teste do ambiente; `SCI_TEST_NEW=0`.
* `SHA256_DRIVE`: relê bytes de arquivo previamente autorizado, confere SHA-256; `SCI_TEST_NEW=0`.
* `RESERVADO`: lease de 20 min, com ID determinístico por tentativa.
* `PERSISTIDO_VERIFICADO`: resultado e manifesto recuperados do Drive, registro `TRABALHOS` relido com todas as 21 colunas.
* `AUTH_REQUIRED`: credencial não concedida, expirada ou sem escopo; nenhum sucesso é fabricado.

O protocolo é *fail closed*: o executor é desligado até existir autorização OAuth do dono do Gmail. O conector do ChatGPT não transfere sua credencial para o Actions. Credenciais nunca devem ser enviadas no chat, em arquivo do repositório ou em logs.

## Testes

```bash
python3 -m unittest discover -s tests -v
python3 nexo_bridge.py --self-test
```

## Autorização OAuth local (sem enviar credenciais ao NEXO)

No Google Cloud, habilite **Google Drive API** e **Google Sheets API**, configure a tela de consentimento e crie um **OAuth client do tipo Desktop app**. Inclua o usuário dono dos arquivos na autorização. A configuração externa em *Testing* pode expirar o refresh token após sete dias; configurar o ciclo de vida da aplicação antes de contar com agendamento permanente.

No computador que fará o consentimento **uma vez**, execute:

```bash
python -m pip install google-auth-oauthlib
python oauth_bootstrap.py --client-json caminho/para/client_secret.json
```

A autorização abre o navegador; o token é salvo **somente** no arquivo local `~/.nexo/oauth.json`, fora do repositório. Copie os três valores diretamente para **Settings > Secrets and variables > Actions** no repositório privado, sem colar no chat. Acrescente `NEXO_TOWER_ID` e `NEXO_ACHADOS_FOLDER_ID` como segredos. O escopo `spreadsheets` pode ler e editar as planilhas às quais o usuário tem acesso; `drive.file` restringe o Drive aos arquivos criados/explicitamente autorizados à aplicação. A especificação técnica de smoke criada antes desse consentimento também precisa estar autorizada, caso contrário a execução retorna `AUTH_REQUIRED`.

## Ativação privada (ação humana necessária)

1. Criar cliente OAuth de aplicação Google Cloud com Drive API e Sheets API habilitadas; completar o consentimento com o usuário dono dos arquivos. `drive.file` exige que os arquivos já existentes necessários sejam explicitamente autorizados à aplicação; a configuração externa em *Testing* pode gerar refresh token expirando em sete dias.
2. Adicionar os cinco segredos apenas ao repositório **privado** de execução: `NEXO_OAUTH_CLIENT_ID`, `NEXO_OAUTH_CLIENT_SECRET`, `NEXO_OAUTH_REFRESH_TOKEN`, `NEXO_TOWER_ID` e `NEXO_ACHADOS_FOLDER_ID`.
3. Autorizar a aplicação para a Tower existente, o arquivo de especificação e os arquivos/pastas de destino. Criar uma especificação `TECH_SMOKE` em arquivo Google Drive e registrar uma linha em `TRABALHOS` com `executor=ACTIONS`, `status=PRONTO`, SHA-256 do JSON e `spec_id` real. Uma especificação tem exatamente os campos `version`, `recipe`, `work_id`, `family_id`.
4. Executar manualmente o workflow do repositório privado e conferir `PERSISTIDO_VERIFICADO` com leitura independente do resultado e do manifesto. Repetir o workflow para comprovar idempotência e simular interrupção após upload.
5. Apenas então habilitar a variável de repositório `NEXO_BRIDGE_ENABLED=true` para agendamento. Não habilitar em repo público com dados ou segredos privados.

**Nota:** `SHA256_DRIVE` não prova completude instrumental ou valor científico. Evidência G3, novelty e replicação permanecem sob as regras de SCIENCE e S11.

## Contrato de fila

A ponte lê a aba `TRABALHOS` da Tower existente (A:U, 21 campos). Seleciona `PRONTO`/`FILA` com executor `ACTIONS`, ou retoma lease expirado. Eventos são acrescentados por `spreadsheets.batchUpdate.appendCells`, preservando as linhas antigas; o consumidor serializado é o único autor de reservas remotas. Os nomes dos arquivos remotos são estáveis por `work_id` e revisão. Uma tentativa incompleta nunca é considerada confirmada só porque houve um resumo textual na planilha.

## Limite operacional atual

A ponte implementa persistência e verificação de entradas pequenas, sem qualquer verossimilhança cosmológica. Não é uma substituição das receitas científicas das frentes. Novas receitas devem entrar por alteração de código versionado, revisão e testes, nunca por shell arbitrário extraído da Tower.
