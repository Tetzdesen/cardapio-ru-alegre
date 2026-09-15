## 1. Agendamento

- [x] 1.1 Trocar os dois `cron` em `.github/workflows/cardapio.yml` por
  `"40 8 * * 1-5"` (05:40 BRT, anúncio do dia) e `"30 12 * * 1-5"` (09h30 BRT,
  reconferência, inalterado); verificar que os comentários ao lado citam o horário
  BRT correto e que a prévia `0 23 * * 0-4` sumiu
- [x] 1.2 Inverter o `if` do passo "Enviar cardápio" para testar o cron da
  reconferência (`30 12 * * 1-5` → `almoco,jantar`) e deixar o anúncio do dia inteiro
  (`desjejum,almoco,jantar`) como ramo padrão; verificar que `workflow_dispatch`, que
  chega com `github.event.schedule` vazio, cai no ramo padrão
- [x] 1.3 Tirar `DIA` de dentro do `if` — os dois runs falam do dia corrente; verificar
  que não sobrou nenhum `date -d "+1 day"` no arquivo
- [x] 1.4 Validar o YAML e simular os dois ramos localmente com o mesmo shell do
  Actions (`bash -c` com `github.event.schedule` fixado em cada valor), conferindo que
  imprimem a data de hoje e a lista de refeições esperada

## 2. Documentação

- [x] 2.1 Atualizar a seção de agendamento do README: horários novos, o fim da prévia
  da véspera, e a conversão UTC (`08:40` e `12:30`); verificar que não sobrou menção a
  20h ou `23` no arquivo
- [x] 2.2 Registrar no README que 05:40 é alvo e não garantia — a fila do Actions
  atrasa de 5 a 20 min — reaproveitando a nota que já existe sobre isso; verificar
  lendo a seção inteira

## 3. Verificação em produção

- [x] 3.1 Subir a mudança antes das 20h BRT, para a prévia da noite não gravar estado
  do dia seguinte e deixar o primeiro 05:40 mudo; verificar com
  `TZ=America/Sao_Paulo date` antes do push
- [ ] 3.2 Disparar o workflow manualmente pela aba Actions e verificar no log que ele
  pediu `desjejum,almoco,jantar` da data de hoje — é a prova do ramo padrão novo
- [ ] 3.3 No dia útil seguinte, verificar que a mensagem das 05:40 (±20 min) chegou com
  as três refeições e que o run das 09h30 não mandou nada
