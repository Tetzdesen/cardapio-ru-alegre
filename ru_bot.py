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
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://restaurante.alegre.ufes.br/cardapio"
USER_AGENT = ("ru-alegre-bot/2.0 (uso pessoal; "
              "+https://github.com/Tetzdesen/cardapio-ru-alegre)")
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

# A pagina diz, em bom portugues, que nao ha cardapio naquela data.
_SEM_CARDAPIO_RE = re.compile(
    r"(n[ãa]o h[áa] card[áa]pio|sem card[áa]pio|card[áa]pio n[ãa]o (?:está |estara |)"
    r"(?:dispon|public)|n[ãa]o haver[áa] (?:card[áa]pio|atendimento|refei)|"
    r"nenhum card[áa]pio)",
    re.IGNORECASE,
)

# Abaixo disso a area de conteudo nao tem texto suficiente para ser uma pagina
# de cardapio de verdade -- tratamos como dia vazio, nao como parser quebrado.
# O rodape institucional sozinho da ~300 caracteres.
LIMIAR_CONTEUDO = 400

log = logging.getLogger("ru_bot")

# Codigos de saida. Qualquer coisa != 0 pinta o job do Actions de vermelho, que e
# o unico canal de alerta que o bot tem.
SAIDA_OK = 0
SAIDA_ERRO_REDE = 2
SAIDA_ERRO_ENVIO = 3
SAIDA_PAGINA_NAO_RECONHECIDA = 4


# --------------------------------------------------------------------------- #
# util
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """minusculo, sem acento, sem pontuacao - para comparar filtros."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


# --------------------------------------------------------------------------- #
# rede
# --------------------------------------------------------------------------- #
TENTATIVAS = 3
ESPERA_BASE = 2.0          # segundos; dobra a cada tentativa
ESPERA_MAXIMA = 60.0       # teto para o retry_after do Telegram

# Repetiveis: o servidor da UFES cai e volta, e o Telegram limita requisicoes.
# 4xx (fora 429) e erro de configuracao ou de rota -- repetir so gasta tempo.
_STATUS_REPETIVEL = {429, 500, 502, 503, 504}
_ERROS_REPETIVEIS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)
# SSLError herda de ConnectionError, mas cadeia de certificado quebrada nao
# conserta sozinha: repetir so atrasa a mensagem de erro que explica o conserto.
_ERROS_DEFINITIVOS = (requests.exceptions.SSLError,)


def _espera_pedida(resp: requests.Response) -> float | None:
    """Le o retry_after que o Telegram manda no 429."""
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    valor = (corpo.get("parameters") or {}).get("retry_after")
    if valor is None:
        valor = resp.headers.get("Retry-After")
    try:
        return min(float(valor), ESPERA_MAXIMA) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _com_retry(chamada, descricao: str, tentativas: int = TENTATIVAS):
    """
    Repete `chamada` em falha transitoria, com espera dobrando a cada vez.

    Devolve a resposta -- inclusive uma resposta de erro definitivo (404, 401),
    que nao e repetida. Erro de rede persistente sobe como excecao.
    """
    erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        espera = ESPERA_BASE * 2 ** (tentativa - 1)
        try:
            resp = chamada()
        except _ERROS_DEFINITIVOS:
            raise
        except _ERROS_REPETIVEIS as e:
            erro = e
            if tentativa == tentativas:
                break
            log.warning("%s falhou (%s); tentativa %d de %d em %.0fs",
                        descricao, e, tentativa + 1, tentativas, espera)
            time.sleep(espera)
            continue

        if resp.status_code not in _STATUS_REPETIVEL or tentativa == tentativas:
            return resp

        espera = _espera_pedida(resp) or espera
        log.warning("%s respondeu %d; tentativa %d de %d em %.0fs",
                    descricao, resp.status_code, tentativa + 1, tentativas, espera)
        time.sleep(espera)

    log.error("%s falhou nas %d tentativas: %s", descricao, tentativas, erro)
    raise erro


def _post_com_retry(url: str, carga: dict) -> requests.Response:
    return _com_retry(
        lambda: requests.post(url, json=carga, timeout=TIMEOUT), "Telegram")


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
    verificacao = _ca_bundle()
    try:
        resp = _com_retry(
            lambda: requests.get(url, headers={"User-Agent": USER_AGENT},
                                 timeout=TIMEOUT, verify=verificacao),
            f"GET {url}",
        )
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


class Pagina(NamedTuple):
    """A pagina depois de limpa: linhas de texto e pistas sobre a estrutura."""

    linhas: list[str]
    rotulos: set[str]      # textos que o HTML marca como rotulo de secao
    tamanho: int           # caracteres de texto na area de conteudo


class Cardapio(NamedTuple):
    """Resultado do parse.

    `reconhecida` e False so quando a pagina baixou, tem volume de texto de
    pagina de conteudo, nao diz que esta sem cardapio, e mesmo assim nenhum
    cabecalho de refeicao casou -- ou seja, o site mudou e o parser ficou cego.
    Dia sem cardapio publicado continua sendo `reconhecida=True` com `blocos`
    vazio: silencio legitimo, nao falha.
    """

    blocos: list[dict]
    reconhecida: bool
    avisos: list[str]


def _rotulos_marcados(area) -> set[str]:
    """
    Textos que o HTML apresenta como rotulo de secao.

    No site, rotulo e `<p><strong>Entrada</strong></p>` e item e `<p>Pirao</p>`.
    Usamos essa marcacao -- e nao o formato do texto -- porque itens e rotulos
    sao lexicalmente identicos ("Pirao", "Laranja" tem a mesma cara de rotulo).
    """
    marcados = set()
    for forte in area.find_all(["strong", "b"]):
        texto = re.sub(r"\s+", " ", forte.get_text()).strip()
        if not texto:
            continue
        pai = forte.parent
        if pai is not None and re.sub(r"\s+", " ", pai.get_text()).strip() == texto:
            marcados.add(normalizar(texto))
    return marcados


def _ler_pagina(html_txt: str) -> Pagina:
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

    return Pagina(linhas, _rotulos_marcados(area), len(area.get_text(strip=True)))


def _categoria_de(linha: str) -> str | None:
    """Devolve o rotulo canonico se a linha inteira for um rotulo de secao."""
    if not _CATEGORIAS_NORM:
        _CATEGORIAS_NORM.update({normalizar(c): c for c in CATEGORIAS})
    return _CATEGORIAS_NORM.get(normalizar(linha))


def analisar(html_txt: str) -> Cardapio:
    """Parseia a pagina e diz se a estrutura dela ainda foi reconhecida."""
    pagina = _ler_pagina(html_txt)
    blocos: list[dict] = []
    avisos: list[str] = []
    atual: dict | None = None
    esperando_data = False
    viu_cabecalho = False

    for linha in pagina.linhas:
        cabecalho = _HEADER_RE.match(linha)
        if cabecalho:
            viu_cabecalho = True
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
        if categoria is None and normalizar(linha) in pagina.rotulos:
            # o site marcou como rotulo, mas nao esta em CATEGORIAS: abre a secao
            # mesmo assim (o conteudo continua saindo) e avisa, para a lista ser
            # atualizada antes que alguem note a falta pelo grupo do Telegram.
            categoria = linha
            aviso = f"rotulo de secao desconhecido: {linha!r} (adicione em CATEGORIAS)"
            avisos.append(aviso)
            log.warning(aviso)

        if categoria:
            atual["secoes"].append((categoria, []))
        elif atual["secoes"]:
            atual["secoes"][-1][1].append(linha)
        else:  # item antes de qualquer rotulo
            atual["secoes"].append(("", [linha]))

    # descarta blocos vazios (cabecalho sem itens)
    blocos = [b for b in blocos if any(itens for _, itens in b["secoes"])]

    reconhecida = (
        viu_cabecalho
        or bool(_SEM_CARDAPIO_RE.search(" ".join(pagina.linhas)))
        or pagina.tamanho < LIMIAR_CONTEUDO
    )
    return Cardapio(blocos, reconhecida, avisos)


def parsear(html_txt: str) -> list[dict]:
    """Devolve so os blocos de refeicao; use `analisar` para saber de falha."""
    return analisar(html_txt).blocos


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
class Peca(NamedTuple):
    """Um pedaco da mensagem e a chave de estado que ele confirma, se houver."""

    chave: str | None
    texto: str


def formatar_bloco(bloco: dict) -> str:
    """Texto de uma refeicao isolada -- e o que entra na assinatura do estado."""
    icone = EMOJI.get(normalizar(bloco["refeicao"]), "🍽️")
    partes = [
        f"{icone} <b>{html.escape(bloco['refeicao'])}</b> — {html.escape(bloco['data'])}\n"
        f"<i>{html.escape(bloco['campus'])}</i>"
    ]
    for categoria, itens in bloco["secoes"]:
        if not itens:
            continue
        if categoria:
            partes.append(f"\n<b>{html.escape(categoria)}</b>")
        for item in itens:
            partes.append(f"• {html.escape(item)}")
    return "\n".join(partes)


def montar(blocos: list[dict], url: str, dia: date | None = None,
           aviso: bool = False) -> list[Peca]:
    """Monta a mensagem em pecas rastreaveis ate a refeicao que cada uma leva."""
    pecas: list[Peca] = []
    if aviso:
        pecas.append(Peca(None, AVISO_MUDANCA))
    for bloco in blocos:
        chave = chave_estado(dia, bloco["refeicao"]) if dia else None
        pecas.append(Peca(chave, formatar_bloco(bloco)))
    pecas.append(Peca(None, f'<a href="{url}">ver no site</a>'))
    return pecas


def juntar(pecas: list[Peca]) -> str:
    return "\n\n".join(p.texto for p in pecas).strip()


def formatar(blocos: list[dict], url: str) -> str:
    if not blocos:
        return "🍽️ <b>RU UFES Alegre</b>\n\nSem cardápio publicado para hoje."
    return juntar(montar(blocos, url))


def para_texto_puro(texto_html: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto_html))


# --------------------------------------------------------------------------- #
# estado (para detectar mudancas entre execucoes)
# --------------------------------------------------------------------------- #
_REFEICOES_NORM = {normalizar(r) for r in REFEICOES}


def chave_estado(dia: date, refeicao: str) -> str:
    """Uma entrada por (dia, refeicao).

    A chave NAO pode depender de quais refeicoes o run pediu: a previa da noite
    manda desjejum+almoco+jantar e a reconferencia da manha so almoco+jantar --
    se o run entrasse na chave, os dois nunca se encontrariam e a da manha
    reenviaria o dia inteiro todo dia.
    """
    return f"{dia.isoformat()}|{normalizar(refeicao)}"


def _chave_valida(chave: str) -> bool:
    dia, _, refeicao = chave.partition("|")
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia)) and refeicao in _REFEICOES_NORM


def carregar_estado(caminho: str) -> dict:
    """Le o estado, ignorando o que nao entende (formato antigo, lixo, corrupcao)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        log.warning("estado em %s ilegível (%s); tratando como vazio", caminho, e)
        return {}

    if not isinstance(dados, dict):
        log.warning("estado em %s não é um objeto JSON; tratando como vazio", caminho)
        return {}

    valido = {
        k: v for k, v in dados.items()
        if isinstance(k, str) and isinstance(v, str) and _chave_valida(k)
    }
    if len(valido) < len(dados):
        log.info("estado: %d entrada(s) em formato desconhecido ignorada(s)",
                 len(dados) - len(valido))
    return valido


def salvar_estado(caminho: str, dados: dict, dias: int = 30) -> None:
    """Grava o estado, descartando entradas mais velhas que `dias`."""
    limite = (datetime.now(TZ_BR).date() - timedelta(days=dias)).isoformat()
    podado = {
        k: v for k, v in dados.items()
        if _chave_valida(k) and k.split("|")[0] >= limite
    }
    pasta = os.path.dirname(os.path.abspath(caminho))
    os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(podado, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def assinatura(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def assinatura_bloco(bloco: dict) -> str:
    """Assina uma refeicao isolada, sem depender das outras que foram no mesmo run."""
    return assinatura(formatar_bloco(bloco))


# --------------------------------------------------------------------------- #
# telegram
# --------------------------------------------------------------------------- #
class FalhaDeEnvio(RuntimeError):
    """Envio interrompido. `confirmadas` traz as chaves que o Telegram ja aceitou."""

    def __init__(self, mensagem: str, confirmadas: list[str]):
        super().__init__(mensagem)
        self.confirmadas = confirmadas


def _agrupar(pecas: list[Peca], limite: int = 4000) -> list[tuple[list[str], str]]:
    """
    Junta pecas em mensagens de ate `limite` caracteres, sem partir uma peca ao
    meio -- e o que permite saber, na falha, quais refeicoes ja chegaram.
    """
    mensagens: list[tuple[list[str], str]] = []
    chaves: list[str] = []
    atual = ""
    for peca in pecas:
        candidato = f"{atual}\n\n{peca.texto}" if atual else peca.texto
        if atual and len(candidato) > limite:
            mensagens.append((chaves, atual))
            chaves, atual = [], peca.texto
        else:
            atual = candidato
        if peca.chave:
            chaves.append(peca.chave)
    if atual.strip():
        mensagens.append((chaves, atual))
    return mensagens


def enviar_telegram(token: str, chat_id: str, pecas: list[Peca]) -> list[str]:
    """Envia a mensagem e devolve as chaves de estado que o Telegram confirmou."""
    confirmadas: list[str] = []
    for chaves, texto in _agrupar(pecas):
        try:
            resp = _post_com_retry(
                f"https://api.telegram.org/bot{token}/sendMessage",
                {
                    "chat_id": chat_id,
                    "text": texto.strip(),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except requests.RequestException as e:
            raise FalhaDeEnvio(f"erro de rede ao falar com o Telegram: {e}",
                               confirmadas) from e
        if not resp.ok:
            raise FalhaDeEnvio(
                f"Telegram respondeu {resp.status_code}: {resp.text}", confirmadas)
        confirmadas.extend(chaves)
    return confirmadas


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
    p.add_argument("--log", default="info",
                   choices=("debug", "info", "warning", "error"),
                   help="nível de log, escrito no stderr (padrão: info)")
    args = p.parse_args(argv)

    # o cardapio sai no stdout; log vai pro stderr, para `--print > arquivo` servir
    logging.basicConfig(level=getattr(logging, args.log.upper()),
                        format="%(levelname)s: %(message)s", stream=sys.stderr)

    dia = datetime.strptime(args.data, "%Y-%m-%d").date() if args.data else None
    url = BASE_URL if dia is None else f"{BASE_URL}/{dia.isoformat()}"

    try:
        pagina = baixar(dia)
    except requests.RequestException as e:
        log.error("erro ao baixar a página: %s", e)
        return 2

    if args.dump_html:
        with open(args.dump_html, "w", encoding="utf-8") as f:
            f.write(pagina)
        log.info("HTML salvo em %s (%d bytes)", args.dump_html, len(pagina))
        return 0

    cardapio = analisar(pagina)
    if not cardapio.reconhecida:
        log.error(
            "nenhum cabeçalho de refeição reconhecido em %s — a estrutura do site "
            "provavelmente mudou. Rode 'ru_bot.py --dump-html pagina.html' e ajuste "
            "o parser (_HEADER_RE / CATEGORIAS).", url,
        )
        return SAIDA_PAGINA_NAO_RECONHECIDA
    blocos = cardapio.blocos

    refeicoes = [] if args.refeicoes.strip().lower() in ("todas", "") \
        else args.refeicoes.split(",")
    # aceita "almoco" e "café da manhã" indistintamente
    equivalentes = {"cafe da manha": ["Desjejum", "Café da Manhã"]}
    expandidas: list[str] = []
    for r in refeicoes:
        expandidas.extend(equivalentes.get(normalizar(r), [r]))

    selecionados = filtrar(blocos, expandidas, args.campus or None)

    if not selecionados and args.vazio_silencioso:
        log.info("nada a enviar hoje")
        return SAIDA_OK

    # Compara refeicao a refeicao com o ultimo envio: o que nao mudou fica de fora,
    # e o aviso so aparece se alguma refeicao ja anunciada mudou de conteudo.
    dia_ref = dia or datetime.now(TZ_BR).date()
    estado = carregar_estado(args.estado) if args.estado else None
    marcas: dict[str, str] = {}
    mudou = False

    if estado is not None:
        novidades = []
        for bloco in selecionados:
            chave = chave_estado(dia_ref, bloco["refeicao"])
            marca = assinatura_bloco(bloco)
            anterior = estado.get(chave)
            if anterior == marca:
                log.debug("%s sem mudança desde o último envio", chave)
                continue
            mudou = mudou or anterior is not None
            marcas[chave] = marca
            novidades.append(bloco)
        selecionados = novidades

        if not selecionados:
            log.info("sem mudança desde o último envio")
            return SAIDA_OK

    if selecionados:
        pecas = montar(selecionados, url,
                       dia_ref if estado is not None else None, aviso=mudou)
    else:  # sem --vazio-silencioso: avisa que hoje não tem
        pecas = [Peca(None, formatar([], url))]
    mensagem = juntar(pecas)

    if args.enviar:
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            log.error("defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID")
            return SAIDA_ERRO_REDE

        codigo = SAIDA_OK
        try:
            confirmadas = enviar_telegram(token, chat_id, pecas)
        except FalhaDeEnvio as e:
            log.error("falha ao enviar: %s", e)
            confirmadas, codigo = e.confirmadas, SAIDA_ERRO_ENVIO

        # so grava o que o Telegram confirmou: o que nao chegou volta amanha
        if estado is not None and confirmadas:
            estado.update({c: marcas[c] for c in confirmadas})
            salvar_estado(args.estado, estado)
        quantas = len(confirmadas) if estado is not None else len(selecionados)
        if quantas or codigo == SAIDA_OK:
            log.info("enviado: %d refeição/ões%s", quantas,
                     " (cardápio alterado)" if mudou else "")
        return codigo

    print(para_texto_puro(mensagem))
    if estado is not None:
        log.info("[estado] %s | %s", ", ".join(sorted(marcas)) or "nada novo",
                 "ALTERADO" if mudou else "primeiro envio")

    return SAIDA_OK


if __name__ == "__main__":
    raise SystemExit(main())
