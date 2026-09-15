## Why

O cardápio chega ao grupo na véspera às 20h. A pedido, o anúncio passa para as
05:40 da manhã do próprio dia — na hora em que quem vai ao RU está acordando e
decidindo se toma café em casa ou no restaurante, em vez de na noite anterior.

A troca não é só de horário. Desde que o bot passou a deduplicar por refeição,
manter a prévia das 20h **e** somar um run às 05:40 deixaria o das 05:40 calado
na maioria dos dias: o cardápio já teria sido anunciado e não teria mudado. Para
o anúncio das 05:40 chegar todo dia, ele precisa ser o primeiro da jornada.

## What Changes

- **A prévia das 20h (dom–qui) sai de cena.** O cardápio deixa de ser anunciado
  na véspera.
- **Novo anúncio às 05:40 BRT (seg–sex)** com o dia inteiro — desjejum, almoço e
  jantar da data corrente. Como nenhuma refeição foi anunciada ainda, tudo é
  novidade e a mensagem sai todo dia útil.
- **A reconferência das 09h30 BRT (seg–sex) continua igual**: pede almoço e
  jantar do dia e só fala se algo mudou desde as 05:40.
- **A execução manual (`workflow_dispatch`) passa a mandar o dia inteiro.** Hoje
  ela cai no ramo da reconferência e omite o desjejum — efeito colateral de o
  `if` do workflow testar o cron da noite. Com o novo formato ela vira o caso
  padrão, que é o comportamento útil para o botão "Run workflow".
- **README atualizado** com os horários novos.

## Capabilities

### New Capabilities

(nenhuma)

### Modified Capabilities

(nenhuma — `skip_specs: true`)

O `ru_bot.py` não muda uma linha. Os horários vivem no cron do GitHub Actions, e
quais refeições cada run pede já são argumentos de linha de comando que o bot
aceita hoje. As capacidades `coleta-cardapio` e `notificacao-cardapio` descrevem
o que o bot faz quando é executado, não quando ele é executado — nenhum requisito
delas muda.

## Impact

- `.github/workflows/cardapio.yml`: os dois `cron` e o `if` que escolhe data e
  refeições.
- `README.md`: a seção de agendamento.
- Nada em `ru_bot.py`, `tests/` ou no formato do arquivo de estado.

## Efeito colateral a registrar

A redação de um cenário do change `melhorar-confiabilidade-bot` (ainda não
arquivado) fala em "Prévia da noite e reconferência da manhã". O requisito
continua valendo — estado por refeição, independente de quais refeições o run
pediu — mas o nome do cenário vai descrever um horário que deixou de existir.
Vale corrigir a redação para "anúncio da manhã e reconferência" antes de
arquivar aquele change.
