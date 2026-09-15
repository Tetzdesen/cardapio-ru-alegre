# Bot do cardápio — RU UFES Alegre → Telegram

Lê `https://restaurante.alegre.ufes.br/cardapio` e manda o cardápio do dia num chat do Telegram.

## 1. Criar o bot

1. Fale com o [@BotFather](https://t.me/BotFather) no Telegram → `/newbot` → guarde o token.
2. Pegue o `chat_id` de destino:
   - conversa pessoal: mande qualquer mensagem pro seu bot e abra
     `https://api.telegram.org/bot<TOKEN>/getUpdates` — o id está em `message.chat.id`;
   - grupo: adicione o bot ao grupo, mande uma mensagem e use o mesmo `getUpdates`
     (ids de grupo são negativos, tipo `-1001234567890`);
   - canal: adicione o bot como administrador e use `@nome_do_canal` como chat_id.

## 2. Rodar local

```bash
pip install -r requirements.txt

python ru_bot.py --print                       # confere a saída antes de enviar

export TELEGRAM_TOKEN=123456:AA...
export TELEGRAM_CHAT_ID=-100123456789
python ru_bot.py --enviar
```

Opções úteis:

| flag | efeito |
|---|---|
| `--data 2026-09-15` | um dia específico (a URL vira `/cardapio/AAAA-MM-DD`) |
| `--refeicoes almoco,jantar` | quais refeições enviar (`todas` para tudo) |
| `--campus alegre` | filtra o campus; vazio traz Alegre e Jerônimo Monteiro |
| `--vazio-silencioso` | não manda nada quando não há cardápio publicado |
| `--estado estado/ultimo-envio.json` | lembra o que já foi enviado; só reenvia refeição que mudou |
| `--log debug` | nível de log no stderr (`debug`, `info`, `warning`, `error`) |
| `--dump-html pagina.html` | salva o HTML cru pra depurar o parser |

O cardápio sai no **stdout**; log vai no **stderr**. Então `--print > cardapio.txt`
guarda só o cardápio.

### Códigos de saída

| código | significado |
|---|---|
| `0` | tudo certo — inclusive "hoje não tem cardápio publicado" |
| `2` | erro de rede depois de esgotar as tentativas, ou falta `TELEGRAM_TOKEN`/`CHAT_ID` |
| `3` | o Telegram recusou o envio |
| `4` | a página baixou mas o parser não reconheceu nada — **o site provavelmente mudou** |

O `4` é o que faz o job do GitHub Actions ficar vermelho e te mandar e-mail. Sem ele,
uma reforma no site da UFES deixaria o bot mudo sem ninguém perceber.

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Nenhum teste toca a rede: todos rodam contra as páginas congeladas em
`tests/fixtures/` (uma página real com as três refeições, uma de dia sem cardápio e
uma simulando o site reformado). Se você mexer no parser, é essa suíte que avisa se
quebrou.

## 3. Agendar de graça (GitHub Actions)

1. Suba o repositório no GitHub.
2. Settings → Secrets and variables → Actions → New repository secret:
   `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
3. O workflow em `.github/workflows/cardapio.yml` roda de segunda a sexta:

| horário (BRT) | o que faz | refeições |
|---|---|---|
| **05h40** | anuncia o cardápio do dia | desjejum, almoço, jantar |
| **09h30** | reconfere e só fala se algo mudou | almoço, jantar |

O botão **Run workflow** (execução manual) faz o mesmo que as 05h40: manda o dia
inteiro.

O arquivo `estado/ultimo-envio.json` guarda uma assinatura **por refeição**
(`2026-09-15|almoco`), não por execução. É isso que faz a reconferência das 09h30 ficar
calada quando nada mudou, e mandar só o almoço quando só o almoço mudou. O workflow
commita esse arquivo de volta no repo a cada envio.

> Na primeira execução depois de atualizar o bot, o cardápio do dia é reenviado uma
> vez: as chaves do formato antigo não casam com o novo e são descartadas.

Dois detalhes do Actions: o cron é em **UTC** (por isso `08:40` e `12:30` no arquivo),
e a fila do GitHub costuma atrasar de 5 a 20 minutos — ou seja, **05h40 é alvo, não
garantia**: na prática a mensagem cai entre 05h45 e 06h00. Se precisar de horário
cravado, use um servidor com `cron` de verdade ou um agendador tipo Cloud Scheduler.

Rodando em servidor próprio, a linha do crontab fica:

```
0 10 * * 1-5 cd /caminho/ru-bot && TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... /usr/bin/python3 ru_bot.py --refeicoes almoco --enviar --vazio-silencioso
```

## Se o parser quebrar

O site é um Plone da UFES e a estrutura muda de vez em quando. O parser não depende de
classes CSS — ele acha os cabeçalhos por regex (`Almoço (Alegre) - sexta-feira, ...`) e
usa a lista de rótulos em `CATEGORIAS` para separar as seções.

Duas coisas avisam antes de virar problema:

- **Rótulo novo** ("Molho", "Prato Vegano"): o bot loga
  `WARNING: rotulo de secao desconhecido: 'Molho'` e mesmo assim abre a seção — o
  conteúdo continua saindo. Adicione o rótulo em `CATEGORIAS` para calar o aviso.
  A detecção usa a marcação do site (`<p><strong>Rótulo</strong></p>`), e não o formato
  do texto, porque itens e rótulos são lexicalmente idênticos ("Pirão", "Laranja").
- **Estrutura irreconhecível**: o bot sai com código `4` e o Actions falha.

Para inspecionar:

```bash
python ru_bot.py --dump-html pagina.html
```

## Cuidados

O RU não tem API pública, então isso é scraping. Rode uma ou duas vezes por dia (é o que
o agendamento faz) e mantenha um `User-Agent` identificável — está no topo do `ru_bot.py`
e aponta para este repositório.

Falha passageira do servidor (timeout, 502) é repetida 3 vezes com espera dobrando;
erro definitivo (404, certificado inválido) não é repetido. A verificação de TLS fica
sempre ligada: o `rnp-icpedu.pem` ao lado do script completa a cadeia que o servidor da
UFES não envia.
