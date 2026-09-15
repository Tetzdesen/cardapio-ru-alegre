## Why

O bot silencia sem avisar. Quando a UFES mexe no HTML do Plone, `parsear()` devolve
uma lista vazia, o script sai com código 0 e o GitHub Actions fica verde — "site
mudou" é indistinguível de "não tem cardápio hoje". E a deduplicação não funciona:
a chave de estado inclui a lista de refeições, então a prévia da noite
(`desjejum,almoco,jantar`) e a reconferência da manhã (`almoco,jantar`) nunca se
encontram, e o run das 09h30 reenvia o cardápio inteiro todos os dias sem nunca
marcar o que mudou.

## What Changes

- **Estado por refeição**: a chave passa a ser `(dia, refeição)` em vez de
  `(dia, lista-de-refeições-do-run)`, e a comparação é feita bloco a bloco. Cada
  refeição é enviada uma vez; nos runs seguintes só reaparece se o conteúdo dela
  mudou, aí com o aviso `⚠️`. **BREAKING**: o formato do arquivo de estado muda —
  chaves antigas são ignoradas, e o primeiro run depois do deploy reenvia o dia.
- **Falha de parser é falha**: se a página baixa com sucesso mas nenhum bloco de
  refeição é reconhecido, o bot sai com código ≠ 0 mesmo sob `--vazio-silencioso`,
  para o Actions ficar vermelho. Página que declara explicitamente não haver
  cardápio continua sendo saída normal.
- **Rótulo desconhecido não é engolido**: uma linha curta que parece rótulo de
  seção mas não está em `CATEGORIAS` vira um aviso no log em vez de virar item da
  seção anterior.
- **Retry com backoff** no download da página e no envio ao Telegram, para um 5xx
  ou soluço de TLS do servidor da UFES não custar o cardápio do dia.
- **Testes de regressão do parser**, usando o `pagina.html` já versionado como
  fixture, mais um fixture de página vazia e um de página com estrutura quebrada.
- **Faxina do repositório**: `gitignore` → `.gitignore` (hoje o arquivo não tem o
  ponto, então não vale nada) e `git rm --cached` em `.venv/` (1291 arquivos) e
  `__pycache__/`. Sem reescrever histórico.

## Capabilities

### New Capabilities
- `coleta-cardapio`: baixar a página do RU e transformá-la em blocos de refeição,
  incluindo o que conta como falha (parser quebrado, rede) versus ausência legítima
  de cardápio.
- `notificacao-cardapio`: decidir o que enviar ao Telegram a cada execução — quais
  refeições são novidade, quais mudaram e quais devem ser omitidas.

### Modified Capabilities

(nenhuma: `openspec/specs/` está vazio, este é o primeiro change do projeto.)

## Impact

- `ru_bot.py`: `baixar`, `parsear`, `chave_estado`, `carregar_estado`,
  `salvar_estado`, `enviar_telegram`, `main`.
- Formato de `estado/ultimo-envio.json` (migração implícita: chaves velhas ficam
  órfãs e são podadas pela regra de 30 dias que já existe).
- `.github/workflows/cardapio.yml`: o job agora falha de verdade quando o parser
  quebra — é isso que gera o e-mail de falha do Actions.
- Novo diretório `tests/` e `pytest` como dependência de desenvolvimento.
- `gitignore` renomeado; `.venv/` e `__pycache__/` saem do índice.

## Premissas registradas

Escolhas feitas sem confirmação, por o pedido ter sido aberto ("como melhorar o bot"):
- Escopo = confiabilidade + testes + faxina do git. Ficaram de fora, como trabalho
  futuro: mostrar o diff textual do que mudou, `editMessageText` em vez de nova
  mensagem, estado no cache do Actions, comandos interativos (`/hoje`), split em
  pacote e CI de lint.
- Limpeza do git por `git rm --cached`, sem `filter-repo` e sem force-push: o
  histórico continua com 12 MB, mas nada é reescrito.
