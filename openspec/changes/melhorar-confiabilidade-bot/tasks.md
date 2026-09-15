## 1. Faxina do repositório e base de testes

- [x] 1.1 Renomear `gitignore` → `.gitignore`, acrescentar `estado/` **não** (o estado é
  commitado de propósito) e verificar com `git check-ignore -v .venv/bin/python` que a
  regra passou a valer
- [x] 1.2 `git rm -r --cached .venv __pycache__` e verificar que `git ls-files | wc -l`
  cai de ~1299 para ~7 e que `git status` fica limpo
- [x] 1.3 Criar `tests/fixtures/` e mover o `pagina.html` versionado para
  `tests/fixtures/pagina-completa.html`; verificar que o arquivo tem os cabeçalhos de
  Almoço e Jantar com `grep -c "Almoço (" tests/fixtures/pagina-completa.html`
- [x] 1.4 Criar `tests/fixtures/pagina-vazia.html` (dia sem cardápio publicado) e
  `tests/fixtures/pagina-quebrada.html` (conteúdo institucional sem nenhum cabeçalho de
  refeição reconhecível); verificar que ambos abrem no BeautifulSoup sem erro
- [x] 1.5 Adicionar `requirements-dev.txt` com `pytest` e verificar que
  `pytest --collect-only` roda sem coletar nada ainda
- [x] 1.6 Escrever `tests/test_parser.py` com o teste do fixture completo — refeições,
  campus, data e ao menos uma seção com itens — e verificar que passa contra o código
  atual (é a rede de segurança para o resto da mudança)

## 2. Falha de parser vira falha de verdade

- [x] 2.1 Fazer o parse distinguir "nenhum cabeçalho reconhecido na página" de "blocos
  reconhecidos, nenhum selecionado", conforme `specs/coleta-cardapio/spec.md`; verificar
  com testes sobre os fixtures vazio e quebrado
- [x] 2.2 No `main`, retornar código ≠ 0 quando o parse não reconheceu a página, mesmo
  com `--vazio-silencioso`, e manter 0 para dia vazio; verificar rodando
  `python ru_bot.py --dump-html` sobre cada fixture e conferindo `echo $?`
- [x] 2.3 Emitir aviso para linha que parece rótulo de seção mas não está em
  `CATEGORIAS`, sem interromper a execução; verificar com um teste que injeta "Molho"
  num fixture e afirma que o aviso saiu e o item continua na saída
- [x] 2.4 Trocar `print`/`sys.stderr` por `logging` com nível configurável; verificar que
  `python ru_bot.py --print` continua imprimindo só o cardápio no stdout

## 3. Estado por refeição

- [x] 3.1 Trocar `chave_estado` para indexar por `(data, refeição normalizada)` e
  descartar chaves em formato antigo na carga; verificar com teste que um estado velho
  não provoca erro e trata as refeições como inéditas
- [x] 3.2 Calcular a assinatura por bloco de refeição em vez de sobre a mensagem inteira;
  verificar com teste que dois blocos iguais em runs diferentes dão a mesma assinatura
- [x] 3.3 Filtrar, antes de formatar, as refeições cuja assinatura não mudou, e aplicar o
  aviso `⚠️` só quando houver refeição alterada; verificar com o teste do ciclo
  noite→manhã: segunda execução com conteúdo idêntico não envia nada e sai 0
- [x] 3.4 Gravar cada entrada de estado só após a confirmação do envio correspondente;
  verificar com teste que simula falha do Telegram e afirma estado inalterado
- [x] 3.5 Tratar arquivo de estado corrompido como estado vazio com aviso; verificar com
  teste que passa um JSON inválido

## 4. Tolerância a falha transitória

- [x] 4.1 Implementar o helper de retry com backoff exponencial (3 tentativas) e lista de
  condições repetíveis; verificar com testes de unidade cobrindo 502→200, esgotamento e
  404 não repetido
- [x] 4.2 Aplicar o retry no download da página, preservando a mensagem de erro de TLS
  que hoje ensina a baixar o intermediário; verificar que o teste de SSL error mantém o
  texto de ajuda
- [x] 4.3 Aplicar o retry no envio ao Telegram, honrando `retry_after` em 429 e não
  repetindo 401/400; verificar com testes de unidade para cada caso

## 5. Fechamento

- [x] 5.1 Trocar o `USER_AGENT` placeholder `seu-email@ufes.br` por um contato real e
  verificar que a string aparece no header da requisição no teste de download
- [x] 5.2 Rodar `pytest` inteiro e confirmar verde; rodar `python ru_bot.py --print`
  contra o site real e conferir que a saída continua igual à de antes da mudança
- [x] 5.3 Atualizar o README: seção de testes, novo comportamento de código de saída, e a
  nota de que o primeiro run após o deploy reenvia o dia; verificar lendo o README de
  ponta a ponta
- [x] 5.4 Executar o workflow por `workflow_dispatch` e verificar nos logs que o run
  seguinte, sem mudança de cardápio, não envia nada
  — verificado pelo run agendado de 2026-09-15 10:40 BRT (o das 09h30, atrasado pela
  fila do Actions) rodando o código novo: descartou as 4 chaves do formato antigo e
  gravou `2026-09-15|almoco` e `|jantar`, com as assinaturas idênticas às calculadas
  localmente. Não foi por `workflow_dispatch` nem por leitura de log, e sim pelo
  commit de estado que o próprio run produziu — evidência mais forte, por ser um run
  de produção de verdade.
