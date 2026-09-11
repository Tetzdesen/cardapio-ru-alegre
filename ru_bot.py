#!/usr/bin/env python3
"""
Bot do cardapio do RU da UFES Alegre -> Telegram.

Uso:
    python ru_bot.py --print                      # so mostra no terminal
    python ru_bot.py --enviar                     # envia pro Telegram
    python ru_bot.py --data 2026-09-11 --print
    python ru_bot.py --refeicoes almoco,jantar --campus alegre --enviar
    python ru_bot.py --dump-html pagina.html      # salva o HTML cru pra depurar

Variaveis de ambiente necessarias para --enviar:
    TELEGRAM_TOKEN    token do bot (pegue no @BotFather)
    TELEGRAM_CHAT_ID  id do chat/grupo/canal de destino
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://restaurante.alegre.ufes.br/cardapio"
USER_AGENT = "ru-alegre-bot/1.0 (uso pessoal; contato: seu-email@ufes.br)"
TIMEOUT = 30

# Fuso de Alegre/ES (sem horario de verao desde 2019)
TZ_BR = timezone(timedelta(hours=-3))

REFEICOES = ["Desjejum", "Café da Manhã", "Cafe da Manha", "Almoço", "Jantar"]

# Rotulos de secao que aparecem dentro de cada refeicao.
CATEGORIAS = [
    "Entrada", "Salada", "Prato Proteico", "Prato Principal", "Opção",
    "Acompanhamento", "Guarnição", "Sobremesa", "Suco", "Refresco",
    "Pão", "Complemento", "Bebida", "Fruta",
]

AVISO_MUDANCA = "⚠️ <b>O cardápio de hoje mudou desde o aviso de ontem.</b>"

EMOJI = {
    "desjejum": "☕",
    "cafe da manha": "☕",
    "almoco": "🍽️",
    "jantar": "🌙",
}

_HEADER_RE = re.compile(
    r"^(?P<refeicao>" + "|".join(REFEICOES) + r")"
    r"(?:\s+\d{2}/\d{2})?\s*"                     # "Almoço 10/09" (as vezes tem a data)
    r"\((?P<campus>[^)]*)\)\s*[-–—]\s*"           # "(Alegre e Jerônimo Monteiro) - "
    r"(?P<data>.*)$",                             # data na mesma linha OU vazia (vem na proxima)
    re.IGNORECASE,
)

# reconhece a linha de data quando ela vem separada do cabecalho
_DATA_RE = re.compile(
    r"^(segunda|terça|quarta|quinta|sexta)-feira|^(sábado|domingo)|^\d{1,2} de \w+ de \d{4}",
    re.IGNORECASE,
)

# rotulo de secao vem sozinho na linha; comparamos o texto inteiro para nao
# fatiar itens que comecam com a mesma palavra (ex.: "Pão Francês" sob "Pão")
_CATEGORIAS_NORM = {}

_FIM_BLOCO_RE = re.compile(
    r"(cardápio poderá sofrer|traços de glúten|CG\s*=|CL\s*=|^\*)", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# util
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """minusculo, sem acento, sem pontuacao - para comparar filtros."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


# --------------------------------------------------------------------------- #
# scraping
# --------------------------------------------------------------------------- #
def _ca_bundle():
    """
    O servidor do RU nao envia o certificado intermediario da RNP/ICPEdu, entao
    a verificacao padrao falha com 'unable to get local issuer certificate'.
    Se o arquivo rnp-icpedu.pem estiver ao lado do script, juntamos ele ao bundle
    do certifi e usamos esse combinado -- a verificacao continua ativa.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    intermediario = os.path.join(base, "rnp-icpedu.pem")
    if not os.path.exists(intermediario):
        return True  # verificacao padrao

    import certifi
    import tempfile

    destino = os.path.join(tempfile.gettempdir(), "ca-ufes-bundle.pem")
    with open(destino, "w", encoding="utf-8") as saida:
        for origem in (certifi.where(), intermediario):
            with open(origem, "r", encoding="utf-8") as entrada:
                saida.write(entrada.read().strip() + "\n")
    return destino


def baixar(dia: date | None = None) -> str:
    url = BASE_URL if dia is None else f"{BASE_URL}/{dia.isoformat()}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                            timeout=TIMEOUT, verify=_ca_bundle())
    except requests.exceptions.SSLError as e:
        raise requests.exceptions.SSLError(
            f"{e}\n\nO servidor da UFES nao envia o certificado intermediario. "
            f"Baixe-o e deixe ao lado deste script:\n"
            f"  curl -sO http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt\n"
            f"  openssl x509 -inform DER -in rnpicpedugr46ovtlsca2025.crt -out rnp-icpedu.pem"
        ) from e
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _extrair_linhas(html_txt: str) -> list[str]:
    soup = BeautifulSoup(html_txt, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # tenta isolar a area de conteudo (Plone/UFES); cai pro body se nao achar
    area = None
    for seletor in ("#content-core", "#content", "#conteudo", "main", "article"):
        area = soup.select_one(seletor)
        if area and len(area.get_text(strip=True)) > 100:
            break
        area = None
    area = area or soup.body or soup

    linhas = []
    for bruta in area.get_text("\n").split("\n"):
        limpa = re.sub(r"\s+", " ", bruta).strip()
        if limpa:
            linhas.append(limpa)
    return linhas


def _categoria_de(linha: str) -> str | None:
    """Devolve o rotulo canonico se a linha inteira for um rotulo de secao."""
    if not _CATEGORIAS_NORM:
        _CATEGORIAS_NORM.update({normalizar(c): c for c in CATEGORIAS})
    return _CATEGORIAS_NORM.get(normalizar(linha))


def parsear(html_txt: str) -> list[dict]:
    """Devolve uma lista de blocos de refeicao encontrados na pagina."""
    blocos: list[dict] = []
    atual: dict | None = None
    esperando_data = False

    for linha in _extrair_linhas(html_txt):
        cabecalho = _HEADER_RE.match(linha)
        if cabecalho:
            data = cabecalho.group("data").strip()
            atual = {
                "refeicao": cabecalho.group("refeicao").strip(),
                "campus": cabecalho.group("campus").strip(),
                "data": data,
                "secoes": [],
            }
            # o site quebra o cabecalho em duas linhas: a data vem na seguinte
            esperando_data = not data
            blocos.append(atual)
            continue

        if atual is None:
            continue

        if esperando_data:
            esperando_data = False
            if _DATA_RE.match(linha):
                atual["data"] = linha
                continue
            # nao era data: segue o fluxo normal e trata como rotulo/item

        if _FIM_BLOCO_RE.search(linha):
            atual = None
            continue

        categoria = _categoria_de(linha)
        if categoria:
            atual["secoes"].append((categoria, []))
        elif atual["secoes"]:
            atual["secoes"][-1][1].append(linha)
        else:  # item antes de qualquer rotulo
            atual["secoes"].append(("", [linha]))

    # descarta blocos vazios (cabecalho sem itens)
    return [b for b in blocos if any(itens for _, itens in b["secoes"])]


def filtrar(blocos: list[dict], refeicoes: list[str], campus: str | None) -> list[dict]:
    alvo_ref = {normalizar(r) for r in refeicoes} if refeicoes else None
    alvo_campus = normalizar(campus) if campus else None

    resultado = []
    for b in blocos:
        if alvo_ref and normalizar(b["refeicao"]) not in alvo_ref:
            continue
        if alvo_campus and alvo_campus not in normalizar(b["campus"]):
            continue
        resultado.append(b)
    return resultado


# --------------------------------------------------------------------------- #
# formatacao
# --------------------------------------------------------------------------- #
def formatar(blocos: list[dict], url: str) -> str:
    if not blocos:
        return "🍽️ <b>RU UFES Alegre</b>\n\nSem cardápio publicado para hoje."

    partes = []
    for b in blocos:
        icone = EMOJI.get(normalizar(b["refeicao"]), "🍽️")
        partes.append(
            f"{icone} <b>{html.escape(b['refeicao'])}</b> — {html.escape(b['data'])}\n"
            f"<i>{html.escape(b['campus'])}</i>"
        )
        for categoria, itens in b["secoes"]:
            if not itens:
                continue
            if categoria:
                partes.append(f"\n<b>{html.escape(categoria)}</b>")
            for item in itens:
                partes.append(f"• {html.escape(item)}")
        partes.append("")

    partes.append(f'<a href="{url}">ver no site</a>')
    return "\n".join(partes).strip()


def para_texto_puro(texto_html: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto_html))


# --------------------------------------------------------------------------- #
# estado (para detectar mudancas entre execucoes)
# --------------------------------------------------------------------------- #
def chave_estado(dia: date, refeicoes: str) -> str:
    return f"{dia.isoformat()}|{normalizar(refeicoes)}"


def carregar_estado(caminho: str) -> dict:
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_estado(caminho: str, dados: dict, dias: int = 30) -> None:
    """Grava o estado, descartando entradas mais velhas que `dias`."""
    limite = (datetime.now(TZ_BR).date() - timedelta(days=dias)).isoformat()
    podado = {k: v for k, v in dados.items() if k.split("|")[0] >= limite}
    pasta = os.path.dirname(os.path.abspath(caminho))
    os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(podado, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def assinatura(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# telegram
# --------------------------------------------------------------------------- #
def enviar_telegram(token: str, chat_id: str, texto: str) -> None:
    limite = 4000  # o limite real e 4096; margem de seguranca
    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > limite:
            pedacos.append(atual)
            atual = ""
        atual += linha + "\n"
    if atual.strip():
        pedacos.append(atual)

    for pedaco in pedacos:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": pedaco.strip(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram respondeu {resp.status_code}: {resp.text}")


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cardápio do RU da UFES Alegre no Telegram")
    p.add_argument("--data", help="AAAA-MM-DD (padrão: hoje)")
    p.add_argument("--refeicoes", default="almoco,jantar",
                   help="lista separada por vírgula, ou 'todas'")
    p.add_argument("--campus", default="alegre",
                   help="filtro de campus ('alegre', 'jeronimo', ou vazio para tudo)")
    p.add_argument("--print", dest="imprimir", action="store_true",
                   help="imprime no terminal em vez de enviar")
    p.add_argument("--enviar", action="store_true", help="envia pro Telegram")
    p.add_argument("--dump-html", metavar="ARQUIVO",
                   help="salva o HTML cru e sai (para depurar o parser)")
    p.add_argument("--vazio-silencioso", action="store_true",
                   help="não envia nada se não houver cardápio")
    p.add_argument("--estado", metavar="ARQUIVO",
                   help="JSON com o último envio; só reenvia se o cardápio mudou")
    args = p.parse_args(argv)

    dia = datetime.strptime(args.data, "%Y-%m-%d").date() if args.data else None
    url = BASE_URL if dia is None else f"{BASE_URL}/{dia.isoformat()}"

    try:
        pagina = baixar(dia)
    except requests.RequestException as e:
        print(f"erro ao baixar a página: {e}", file=sys.stderr)
        return 2

    if args.dump_html:
        with open(args.dump_html, "w", encoding="utf-8") as f:
            f.write(pagina)
        print(f"HTML salvo em {args.dump_html} ({len(pagina)} bytes)")
        return 0

    blocos = parsear(pagina)
    if not blocos:
        print("nenhum bloco de refeição reconhecido — rode com --dump-html para inspecionar",
              file=sys.stderr)

    refeicoes = [] if args.refeicoes.strip().lower() in ("todas", "") \
        else args.refeicoes.split(",")
    # aceita "almoco" e "café da manhã" indistintamente
    equivalentes = {"cafe da manha": ["Desjejum", "Café da Manhã"]}
    expandidas: list[str] = []
    for r in refeicoes:
        expandidas.extend(equivalentes.get(normalizar(r), [r]))

    selecionados = filtrar(blocos, expandidas, args.campus or None)

    if not selecionados and args.vazio_silencioso:
        print("nada a enviar hoje")
        return 0

    mensagem = formatar(selecionados, url)

    # comparacao com o ultimo envio
    estado, chave, marca, mudou = None, None, None, False
    if args.estado:
        estado = carregar_estado(args.estado)
        chave = chave_estado(dia or datetime.now(TZ_BR).date(), args.refeicoes)
        marca = assinatura(mensagem)
        anterior = estado.get(chave)
        if anterior == marca:
            print("sem mudança desde o último envio")
            return 0
        mudou = anterior is not None
        if mudou:
            mensagem = AVISO_MUDANCA + "\n\n" + mensagem

    if args.enviar:
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID", file=sys.stderr)
            return 2
        try:
            enviar_telegram(token, chat_id, mensagem)
        except Exception as e:
            print(f"falha ao enviar: {e}", file=sys.stderr)
            return 3
        if estado is not None:  # só grava depois do envio dar certo
            estado[chave] = marca
            salvar_estado(args.estado, estado)
        print("enviado (cardápio alterado)" if mudou else "enviado")
    else:
        print(para_texto_puro(mensagem))
        if estado is not None:
            print(f"\n[estado] chave={chave} assinatura={marca} "
                  f"{'ALTERADO' if mudou else 'primeiro envio'}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
