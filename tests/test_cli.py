"""Códigos de saída do main — é por eles que o GitHub Actions acusa quebra."""

import ru_bot


def test_pagina_quebrada_falha_mesmo_em_silencio(pagina_servida, pagina_quebrada, caplog):
    pagina_servida(pagina_quebrada)
    codigo = ru_bot.main(["--print", "--vazio-silencioso"])
    assert codigo == ru_bot.SAIDA_PAGINA_NAO_RECONHECIDA
    assert "estrutura do site" in caplog.text


def test_dia_vazio_sai_zero(pagina_servida, pagina_vazia, capsys):
    pagina_servida(pagina_vazia)
    assert ru_bot.main(["--print", "--vazio-silencioso"]) == ru_bot.SAIDA_OK
    assert "Sem cardápio" not in capsys.readouterr().out


def test_dia_util_sai_zero_e_imprime(pagina_servida, pagina_completa, capsys):
    pagina_servida(pagina_completa)
    assert ru_bot.main(["--print", "--refeicoes", "almoco"]) == ru_bot.SAIDA_OK
    saida = capsys.readouterr().out
    assert "Almoço" in saida and "Peixe Frito" in saida


def test_refeicao_ausente_nao_e_falha(pagina_servida, pagina_completa):
    """A página foi entendida; só não tem a refeição pedida naquele campus."""
    pagina_servida(pagina_completa)
    assert ru_bot.main(
        ["--print", "--refeicoes", "almoco", "--campus", "vitoria",
         "--vazio-silencioso"]
    ) == ru_bot.SAIDA_OK


def test_stdout_leva_so_o_cardapio(pagina_servida, pagina_completa, capsys):
    """Log vai pro stderr; `--print > arquivo` tem que render só o cardápio."""
    pagina_servida(pagina_completa)
    ru_bot.main(["--print", "--refeicoes", "almoco", "--log", "debug"])
    saida = capsys.readouterr()
    assert "Almoço" in saida.out
    for nivel in ("DEBUG:", "INFO:", "WARNING:", "ERROR:"):
        assert nivel not in saida.out
