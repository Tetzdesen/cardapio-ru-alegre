## Context

Os horários vivem no `cron` do GitHub Actions, em UTC, e um `if` no passo de envio
escolhe data e refeições comparando `github.event.schedule` com a string literal do
cron da noite. O bot recebe tudo por linha de comando e não sabe que horas são.

Motivação e escopo: ver `proposal.md`.

## Goals / Non-Goals

**Goals:**
- Anúncio diário às 05:40 BRT que realmente chega, todo dia útil.
- Transição sem um dia mudo entre o último "prévia das 20h" e o primeiro 05:40.

**Non-Goals:**
- Precisão de horário. A fila do Actions atrasa de 5 a 20 minutos e isso não tem
  conserto dentro do Actions (ver Riscos).
- Mexer no `ru_bot.py`. Se a mudança exigir código, é sinal de que o desenho está
  errado.

## Decisions

### `cron` em UTC: `40 8 * * 1-5`

Alegre é UTC-3 o ano inteiro (sem horário de verão desde 2019), então 05:40 BRT é
08:40 UTC no mesmo dia da semana. A máscara passa de `0-4` (dom–qui, porque a prévia
falava do dia seguinte) para `1-5` (seg–sex, porque o anúncio agora fala do próprio
dia).

### O `if` passa a testar a reconferência, não o anúncio

Hoje o `if` compara com o cron da noite e tudo o mais cai no ramo da reconferência —
por isso o botão "Run workflow" manda só almoço e jantar. Invertendo o teste, o ramo
padrão vira o anúncio do dia inteiro e a reconferência fica no ramo explícito. O
disparo manual passa a fazer a coisa útil sem nenhum código a mais.

Alternativa descartada: um `if` de três ramos com `workflow_dispatch` separado. Mais
linhas para o mesmo resultado.

### A data sai do `if`

Os dois runs falam do dia corrente, então `DIA` vira uma linha só antes do `if`. Só
as refeições dependem do horário: às 05:40 o desjejum ainda vai acontecer, às 09h30
já passou.

## Risks / Trade-offs

- **O dia da virada pode ficar mudo.** Se a mudança subir depois das 20h, a prévia da
  noite já terá anunciado o dia seguinte e gravado o estado — aí o 05:40 seguinte não
  tem novidade para contar e fica calado, parecendo que a mudança não funcionou.
  → Subir antes das 20h BRT. Aí a prévia não roda, o estado do dia seguinte fica
  vazio e o primeiro 05:40 anuncia tudo. Se subir depois, ou espera um dia, ou apaga
  `estado/ultimo-envio.json` antes do 05:40.
- **05:40 é o alvo, não a garantia.** A fila do Actions costuma atrasar 5 a 20 min, o
  que coloca a mensagem entre 05:45 e 06:00. Quem precisa de 05:40 cravado precisa de
  `cron` em servidor próprio ou de um Cloud Scheduler.
  → Se o atraso incomodar, adiantar o cron para `30 8` centra a entrega mais perto
  das 05:40. Fica registrado como ajuste possível, não feito agora.
- **Acaba a prévia da véspera.** Quem se programava na noite anterior perde isso. Foi
  a escolha explícita: ou o anúncio das 05:40 chega todo dia, ou a prévia continua e
  ele fica calado quase sempre.
- **Se a página do dia não estiver publicada às 05:40**, o run sai calado
  (`--vazio-silencioso`) e o desjejum daquele dia não é anunciado — às 09h30 ele já
  passou. O risco é baixo: a página do dia seguinte já existe na véspera à noite, que
  é como a prévia das 20h funcionava.

## Migration Plan

1. Subir a mudança **antes das 20h BRT**.
2. No dia útil seguinte, às 05:40 (±20 min), o grupo recebe o dia inteiro.
3. Às 09h30 o grupo não deve receber nada, a menos que o cardápio tenha mudado.
4. Rollback: reverter o commit devolve a prévia das 20h. O arquivo de estado serve
   aos dois formatos de agenda sem conversão, porque é indexado por (dia, refeição).
