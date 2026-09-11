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
| `--dump-html pagina.html` | salva o HTML cru pra depurar o parser |

## 3. Agendar de graça (GitHub Actions)

1. Suba o repositório no GitHub.
2. Settings → Secrets and variables → Actions → New repository secret:
   `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
3. O workflow em `.github/workflows/cardapio.yml` já roda 10h e 16h (BRT), de segunda a sexta.

Dois detalhes do Actions: o cron é em **UTC** (por isso `13` e `19`), e a fila do GitHub
costuma atrasar de 5 a 20 minutos — se precisar de horário exato, use um servidor com
`cron` de verdade ou um agendador tipo Cloud Scheduler.

Rodando em servidor próprio, a linha do crontab fica:

```
0 10 * * 1-5 cd /caminho/ru-bot && TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... /usr/bin/python3 ru_bot.py --refeicoes almoco --enviar --vazio-silencioso
```

## Se o parser quebrar

O site é um Plone da UFES e a estrutura muda de vez em quando. O parser não depende de
classes CSS — ele acha os cabeçalhos por regex (`Almoço (Alegre) - sexta-feira, ...`) e
usa a lista de rótulos em `CATEGORIAS` para separar as seções. Se aparecer um rótulo novo
("Molho", "Prato Vegano"), basta adicioná-lo nessa lista. Para inspecionar:

```bash
python ru_bot.py --dump-html pagina.html
```

## Cuidados

O RU não tem API pública, então isso é scraping. Rode uma ou duas vezes por dia (é o que
o agendamento faz) e mantenha um `User-Agent` identificável — está no topo do `ru_bot.py`,
troque pelo seu e-mail.
