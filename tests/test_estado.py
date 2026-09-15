"""O bug principal: a reconferência da manhã reenviava o dia inteiro."""

import json
import logging

import pytest

import ru_bot
from test_retry import RespostaFalsa


@pytest.fixture
def telegram(monkeypatch):
    """Captura o que seria enviado; permite forçar falha numa das mensagens."""

    class Telegram:
        def __init__(self):
            self.enviadas = []
            self.falhar_a_partir_de = None

        def post(self, url, json=None, timeout=None):
            self.enviadas.append(json["text"])
            if (self.falhar_a_partir_de is not None
                    and len(self.enviadas) > self.falhar_a_partir_de):
                return RespostaFalsa(400, {"description": "recusado"})
            return RespostaFalsa(200, {"ok": True})

    falso = Telegram()
    monkeypatch.setattr(ru_bot.requests, "post", falso.post)
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:AA")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100")
    return falso


@pytest.fixture
def estado(tmp_path):
    return str(tmp_path / "estado" / "ultimo-envio.json")


def rodar(refeicoes, estado, extra=()):
    return ru_bot.main(
        ["--data", "2026-09-11", "--refeicoes", refeicoes, "--campus", "alegre",
         "--estado", estado, "--enviar", "--vazio-silencioso", *extra]
    )


def test_noite_manda_tudo_e_manha_fica_calada(
        pagina_servida, pagina_completa, telegram, estado):
    """Prévia da noite (3 refeições) e reconferência da manhã (2) se encontram."""
    pagina_servida(pagina_completa)

    assert rodar("desjejum,almoco,jantar", estado) == ru_bot.SAIDA_OK
    assert len(telegram.enviadas) == 1
    assert "Desjejum" in telegram.enviadas[0]

    telegram.enviadas.clear()
    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_OK
    assert telegram.enviadas == []


def test_so_a_refeicao_alterada_volta(
        pagina_servida, pagina_completa, telegram, estado):
    pagina_servida(pagina_completa)
    rodar("almoco,jantar", estado)
    telegram.enviadas.clear()

    pagina_servida(pagina_completa.replace("Peixe Frito", "Frango Assado"))
    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_OK

    assert len(telegram.enviadas) == 1
    mensagem = telegram.enviadas[0]
    assert "Frango Assado" in mensagem
    assert "Jantar" not in mensagem
    assert "mudou desde o aviso" in mensagem


def test_refeicao_inedita_vai_sem_aviso(
        pagina_servida, pagina_completa, telegram, estado):
    pagina_servida(pagina_completa)
    rodar("almoco", estado)
    telegram.enviadas.clear()

    rodar("almoco,jantar", estado)          # jantar nunca foi enviado
    assert len(telegram.enviadas) == 1
    assert "Jantar" in telegram.enviadas[0]
    assert "mudou desde o aviso" not in telegram.enviadas[0]


def test_falha_no_envio_nao_grava_estado(
        pagina_servida, pagina_completa, telegram, estado):
    pagina_servida(pagina_completa)
    telegram.falhar_a_partir_de = 0          # a primeira mensagem já falha

    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_ERRO_ENVIO
    assert ru_bot.carregar_estado(estado) == {}

    telegram.falhar_a_partir_de = None
    telegram.enviadas.clear()
    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_OK
    assert "Almoço" in telegram.enviadas[0]


def test_envio_parcial_so_grava_o_confirmado(
        pagina_servida, pagina_completa, telegram, estado, monkeypatch):
    """Mensagem dividida: o que não foi confirmado volta na próxima execução."""
    monkeypatch.setattr(ru_bot, "_agrupar",
                        lambda pecas, limite=4000: [
                            ([p.chave] if p.chave else [], p.texto) for p in pecas])
    telegram.falhar_a_partir_de = 1          # a segunda mensagem falha

    pagina_servida(pagina_completa)
    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_ERRO_ENVIO

    gravado = ru_bot.carregar_estado(estado)
    assert list(gravado) == ["2026-09-11|almoco"]


def test_estado_de_formato_antigo_e_ignorado(estado, tmp_path, caplog):
    (tmp_path / "estado").mkdir()
    with open(estado, "w", encoding="utf-8") as f:
        json.dump({"2026-09-11|almocojantar": "abc123"}, f)

    with caplog.at_level(logging.INFO, logger="ru_bot"):
        assert ru_bot.carregar_estado(estado) == {}
    assert "formato desconhecido" in caplog.text


def test_estado_antigo_faz_a_refeicao_parecer_inedita(
        pagina_servida, pagina_completa, telegram, estado, tmp_path):
    (tmp_path / "estado").mkdir()
    with open(estado, "w", encoding="utf-8") as f:
        json.dump({"2026-09-11|almocojantar": "abc123"}, f)

    pagina_servida(pagina_completa)
    assert rodar("almoco,jantar", estado) == ru_bot.SAIDA_OK
    assert "Almoço" in telegram.enviadas[0]
    assert "mudou desde o aviso" not in telegram.enviadas[0]


def test_estado_corrompido_vira_estado_vazio(estado, tmp_path, caplog):
    (tmp_path / "estado").mkdir()
    with open(estado, "w", encoding="utf-8") as f:
        f.write("{isso não é json")

    assert ru_bot.carregar_estado(estado) == {}
    assert "ilegível" in caplog.text


def test_estado_velho_e_podado(estado):
    antiga = "2020-01-01|almoco"
    nova = "2026-09-11|almoco"
    ru_bot.salvar_estado(estado, {antiga: "aaa", nova: "bbb"})
    assert list(ru_bot.carregar_estado(estado)) == [nova]


def test_assinatura_do_bloco_independe_dos_vizinhos(pagina_completa):
    blocos = ru_bot.parsear(pagina_completa)
    almoco = [b for b in blocos if b["refeicao"] == "Almoço"][0]
    assert (ru_bot.assinatura_bloco(almoco)
            == ru_bot.assinatura_bloco(dict(almoco)))
