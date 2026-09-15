"""Retry: repete o transitório, respeita o definitivo."""

import pytest
import requests

import ru_bot


class RespostaFalsa:
    def __init__(self, status=200, corpo=None, headers=None):
        self.status_code = status
        self._corpo = corpo or {}
        self.headers = headers or {}
        self.text = str(self._corpo)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._corpo


@pytest.fixture
def sem_espera(monkeypatch):
    """Não dorme de verdade; guarda quanto teria dormido."""
    dormidas = []
    monkeypatch.setattr(ru_bot.time, "sleep", dormidas.append)
    return dormidas


def test_repete_502_e_aceita_o_200(sem_espera):
    respostas = [RespostaFalsa(502), RespostaFalsa(200)]
    resp = ru_bot._com_retry(lambda: respostas.pop(0), "teste")
    assert resp.status_code == 200
    assert sem_espera == [2.0]


def test_backoff_dobra(sem_espera):
    resp = ru_bot._com_retry(lambda: RespostaFalsa(503), "teste")
    assert resp.status_code == 503          # esgotou: devolve a última resposta
    assert sem_espera == [2.0, 4.0]


def test_nao_repete_404(sem_espera):
    chamadas = []

    def chamada():
        chamadas.append(1)
        return RespostaFalsa(404)

    assert ru_bot._com_retry(chamada, "teste").status_code == 404
    assert len(chamadas) == 1
    assert sem_espera == []


def test_nao_repete_401(sem_espera):
    assert ru_bot._com_retry(lambda: RespostaFalsa(401), "teste").status_code == 401
    assert sem_espera == []


def test_erro_de_rede_sobe_apos_esgotar(sem_espera, caplog):
    def cai():
        raise requests.exceptions.ConnectionError("recusou")

    with pytest.raises(requests.exceptions.ConnectionError):
        ru_bot._com_retry(cai, "teste")
    assert sem_espera == [2.0, 4.0]
    assert "falhou nas 3 tentativas" in caplog.text


def test_timeout_e_repetivel(sem_espera):
    respostas = [requests.exceptions.Timeout("estourou"), RespostaFalsa(200)]

    def chamada():
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    assert ru_bot._com_retry(chamada, "teste").status_code == 200


def test_429_respeita_retry_after(sem_espera):
    respostas = [
        RespostaFalsa(429, {"parameters": {"retry_after": 7}}),
        RespostaFalsa(200),
    ]
    ru_bot._com_retry(lambda: respostas.pop(0), "teste")
    assert sem_espera == [7.0]


def test_429_com_retry_after_absurdo_tem_teto(sem_espera):
    respostas = [
        RespostaFalsa(429, {"parameters": {"retry_after": 99999}}),
        RespostaFalsa(200),
    ]
    ru_bot._com_retry(lambda: respostas.pop(0), "teste")
    assert sem_espera == [ru_bot.ESPERA_MAXIMA]


def test_erro_de_certificado_nao_e_repetido(sem_espera):
    """SSLError herda de ConnectionError, mas cadeia quebrada não se conserta."""
    chamadas = []

    def cai():
        chamadas.append(1)
        raise requests.exceptions.SSLError("unable to get local issuer certificate")

    with pytest.raises(requests.exceptions.SSLError):
        ru_bot._com_retry(cai, "teste")
    assert len(chamadas) == 1
    assert sem_espera == []


def test_download_repete_502(sem_espera, monkeypatch):
    respostas = [RespostaFalsa(502), RespostaFalsa(200)]
    for r in respostas:
        r.raise_for_status = lambda: None
        r.apparent_encoding, r.text = "utf-8", "<html>ok</html>"
    monkeypatch.setattr(ru_bot.requests, "get",
                        lambda *a, **k: respostas.pop(0))
    assert ru_bot.baixar() == "<html>ok</html>"


def test_download_preserva_a_ajuda_do_certificado(sem_espera, monkeypatch):
    def cai(*a, **k):
        raise requests.exceptions.SSLError("unable to get local issuer certificate")

    monkeypatch.setattr(ru_bot.requests, "get", cai)
    with pytest.raises(requests.exceptions.SSLError) as erro:
        ru_bot.baixar()
    assert "certificado intermediario" in str(erro.value)
    assert "rnp-icpedu.pem" in str(erro.value)


def test_envio_repete_429_e_confirma(sem_espera, monkeypatch):
    respostas = [
        RespostaFalsa(429, {"parameters": {"retry_after": 3}}),
        RespostaFalsa(200, {"ok": True}),
    ]
    monkeypatch.setattr(ru_bot.requests, "post",
                        lambda *a, **k: respostas.pop(0))
    pecas = [ru_bot.Peca("2026-09-11|almoco", "Almoço")]
    assert ru_bot.enviar_telegram("t", "c", pecas) == ["2026-09-11|almoco"]
    assert sem_espera == [3.0]


def test_envio_nao_repete_401(sem_espera, monkeypatch):
    chamadas = []

    def post(*a, **k):
        chamadas.append(1)
        return RespostaFalsa(401, {"description": "Unauthorized"})

    monkeypatch.setattr(ru_bot.requests, "post", post)
    with pytest.raises(ru_bot.FalhaDeEnvio) as erro:
        ru_bot.enviar_telegram("t", "c", [ru_bot.Peca("k", "oi")])
    assert len(chamadas) == 1
    assert erro.value.confirmadas == []


def test_user_agent_identifica_o_bot(sem_espera, monkeypatch):
    """O RU não tem API pública: o User-Agent é como o bot se identifica."""
    vistos = {}

    def get(url, headers=None, **k):
        vistos.update(headers or {})
        r = RespostaFalsa(200)
        r.raise_for_status, r.apparent_encoding, r.text = (lambda: None), "utf-8", ""
        return r

    monkeypatch.setattr(ru_bot.requests, "get", get)
    ru_bot.baixar()
    assert "ru-alegre-bot" in vistos["User-Agent"]
    assert "seu-email@ufes.br" not in vistos["User-Agent"]
    assert "github.com/Tetzdesen" in vistos["User-Agent"]
