## Context

`ru_bot.py` é um script único de ~400 linhas, sem testes, rodado por cron do GitHub
Actions duas vezes por dia. O estado vive num JSON commitado no próprio repo pelo
workflow. O parser é heurístico sobre um Plone da UFES: acha cabeçalhos por regex e
separa seções por uma allowlist de rótulos.

Duas restrições moldam o desenho: (1) a execução é sem estado a não ser pelo JSON
commitado, então qualquer mudança de formato precisa sobreviver a um arquivo velho no
disco; (2) o único canal de alerta que já existe é o e-mail de falha do Actions, o que
faz do código de saída a interface de erro do bot.

Motivação: ver `proposal.md` — Why. Requisitos: ver `specs/`.

## Goals / Non-Goals

**Goals:**
- Que uma quebra do site vire um Actions vermelho no mesmo dia.
- Que a deduplicação funcione entre execuções com conjuntos diferentes de refeições.
- Cobrir o parser com testes que rodem offline, sem tocar no site da UFES.
- Manter o script executável como `python ru_bot.py` — sem build, sem instalação.

**Non-Goals:**
- Reestruturar em pacote com módulos separados. O arquivo único ainda cabe; separar
  agora só dificultaria o diff desta mudança.
- Trocar o transporte do estado (cache do Actions, gist, banco). O commit no repo é
  feio mas funciona, e mexer nisso é ortogonal.
- Qualquer coisa interativa (comandos `/hoje`), que exigiria processo em execução
  contínua ou webhook.

## Decisions

### Estado indexado por (data, refeição normalizada)

Hoje a chave é `f"{dia}|{normalizar(refeicoes)}"`, onde `refeicoes` é a string crua da
CLI — ou seja, a chave carrega qual run gravou, não o que foi gravado. Passa a ser um
dicionário `{"YYYY-MM-DD|almoco": "<assinatura>"}`, uma entrada por refeição, com a
assinatura calculada sobre o bloco formatado daquela refeição isoladamente.

A decisão embutida: a comparação passa a ser por bloco, não pela mensagem inteira. Isso
é o que permite a execução da manhã omitir o jantar inalterado e mandar só o almoço que
mudou. Como efeito colateral, o cabeçalho com a data entra na assinatura do bloco, o que
é desejável — se a data do bloco muda, é outro cardápio.

Alternativas descartadas: (a) normalizar a lista de refeições na chave — não resolve,
porque conjuntos diferentes continuam gerando chaves diferentes; (b) assinar a página
inteira — qualquer mudança de rodapé dispara reenvio de tudo.

### Um marcador explícito para "não reconheci a página"

`parsear()` devolver `[]` é ambíguo: pode ser site quebrado ou dia sem publicação. Em
vez de espalhar heurísticas pelo `main`, o resultado do parse passa a distinguir os dois
casos — blocos reconhecidos (possivelmente zero após o filtro de campus/refeição) versus
nenhum cabeçalho reconhecido na página inteira.

O critério escolhido: se nenhum cabeçalho de refeição casou **e** a página tem volume de
texto compatível com uma página de conteúdo, é quebra de parser. Página curta ou com
texto explícito de ausência é dia vazio. O limiar de texto é grosseiro de propósito — o
custo de um falso positivo é um e-mail de falha do Actions, e o custo de um falso
negativo é o bot mudo por semanas. Erramos para o lado do alarme.

### Retry como decorador fino, sem nova dependência

`tenacity` resolveria, mas `requirements.txt` hoje tem duas linhas e o bot roda em
runner efêmero: uma função de ~15 linhas com backoff exponencial (3 tentativas, 2s/4s)
e uma lista de exceções/status repetíveis evita a dependência. Para o Telegram, 429 usa
o `retry_after` do corpo da resposta em vez do backoff fixo.

### Testes com fixtures HTML congelados

`pagina.html` (54 KB, já versionado) vira `tests/fixtures/pagina-completa.html`. Somam-se
um fixture de dia sem cardápio e um de página com estrutura destruída (divs sem os
cabeçalhos reconhecíveis). Os testes cobrem: blocos e seções extraídos do fixture
completo, dia vazio saindo 0, estrutura quebrada saindo ≠ 0, rótulo desconhecido gerando
aviso, e o ciclo de estado noite→manhã que é o bug principal. Nenhum teste faz rede;
`requests` é dublado.

### `logging` em vez de `print`

`print`/`sys.stderr` espalhados viram um logger com nível ajustável. No Actions, o
stdout já é capturado — o ganho é poder marcar aviso versus erro e o parser poder emitir
avisos de rótulo desconhecido sem poluir a saída normal.

## Risks / Trade-offs

- **O primeiro run após o deploy reenvia o dia inteiro** (chaves antigas não casam com o
  formato novo) → aceitar; é uma mensagem duplicada, uma vez. A alternativa, um
  migrador de formato, custa mais do que o incômodo que evita.
- **Falso positivo de "parser quebrado" em feriado prolongado**, se a página de dia vazio
  vier com muito texto institucional → o fixture de dia vazio trava esse caso nos
  testes; se acontecer na prática, ajusta-se o limiar, não a regra.
- **`git rm --cached .venv/` mexe no repo de quem já clonou** → é só índice; quem tem
  clone local mantém o diretório em disco, agora ignorado.
- **Envio parcial em mensagem dividida**: se a parte 2 de 3 falhar, as refeições da parte
  1 já foram vistas pelo grupo mas não terão estado gravado, e serão reenviadas. Preferir
  duplicata a omissão é a escolha certa para um bot de cardápio.
- **O retry aumenta a carga no servidor da UFES** → limitado a 3 tentativas com backoff,
  duas vezes por dia; continua desprezível.

## Migration Plan

1. Merge; o estado antigo continua no disco e é ignorado.
2. Primeiro run noturno reenvia o dia seguinte inteiro (esperado).
3. Run da manhã seguinte deve enviar **nada** se o cardápio não mudou — é este o sinal
   de que a correção pegou. Se enviar tudo de novo, o bug continua.
4. Rollback: reverter o commit. O formato de estado novo é ignorado pelo código antigo
   pelo mesmo motivo que o antigo é ignorado pelo novo.
