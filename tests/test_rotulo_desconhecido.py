"""Rótulo novo no site vira aviso, não item engolido na seção anterior."""

import logging

import ru_bot


def com_molho(html: str) -> str:
    """Injeta uma seção 'Molho' — rótulo que não está em CATEGORIAS."""
    return html.replace(
        "<p><strong>Sobremesa</strong></p>",
        "<p><strong>Molho</strong></p>\n<p>Vinagrete</p>\n"
        "<p><strong>Sobremesa</strong></p>",
        1,
    )


def test_avisa_e_nomeia_o_rotulo(pagina_completa, caplog):
    with caplog.at_level(logging.WARNING, logger="ru_bot"):
        resultado = ru_bot.analisar(com_molho(pagina_completa))
    assert any("Molho" in a for a in resultado.avisos)
    assert "Molho" in caplog.text
    assert "CATEGORIAS" in caplog.text


def test_conteudo_continua_saindo(pagina_completa):
    resultado = ru_bot.analisar(com_molho(pagina_completa))
    almoco = resultado.blocos[1]
    assert ("Molho", ["Vinagrete"]) in almoco["secoes"]
    # a sobremesa seguinte não foi contaminada
    assert dict(almoco["secoes"])["Sobremesa"] == ["Laranja"]


def test_execucao_continua_normal(pagina_servida, pagina_completa):
    pagina_servida(com_molho(pagina_completa))
    assert ru_bot.main(["--print", "--refeicoes", "almoco"]) == ru_bot.SAIDA_OK


def test_item_comum_nao_vira_aviso(pagina_completa):
    """'Pirão' e 'Laranja' têm cara de rótulo mas são itens — nada de aviso."""
    assert ru_bot.analisar(pagina_completa).avisos == []
