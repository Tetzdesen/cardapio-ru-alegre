"""Página quebrada é falha; dia sem cardápio é silêncio legítimo."""

import ru_bot


def test_pagina_completa_e_reconhecida(pagina_completa):
    resultado = ru_bot.analisar(pagina_completa)
    assert resultado.reconhecida
    assert len(resultado.blocos) == 3


def test_dia_sem_cardapio_e_reconhecido(pagina_vazia):
    """A página diz que não há cardápio: nada a enviar, mas o parser está vivo."""
    resultado = ru_bot.analisar(pagina_vazia)
    assert resultado.reconhecida
    assert resultado.blocos == []


def test_estrutura_quebrada_nao_e_reconhecida(pagina_quebrada):
    """Conteúdo institucional longo e nenhum cabeçalho: o site mudou."""
    resultado = ru_bot.analisar(pagina_quebrada)
    assert not resultado.reconhecida
    assert resultado.blocos == []


def test_pagina_curta_nao_acusa_falha():
    """Página sem área de conteúdo carregada conta como vazia, não como quebra."""
    resultado = ru_bot.analisar(
        "<html><body><div id='content'><p>Cardápio</p></div></body></html>"
    )
    assert resultado.reconhecida


def test_cabecalho_sem_itens_ainda_e_reconhecido():
    """O cabeçalho casou: o parser enxerga a página, ela é que está vazia."""
    html = (
        "<html><body><div id='content'>"
        "<p>Almoço 11/09 (Alegre e Jerônimo Monteiro) - </p>"
        "<p>sexta-feira, 11 de Setembro de 2026</p>"
        "<p>* O cardápio poderá sofrer alterações sem comunicação prévia.</p>"
        + "<p>Texto institucional de enchimento para passar do limiar.</p>" * 10
        + "</div></body></html>"
    )
    resultado = ru_bot.analisar(html)
    assert resultado.reconhecida
    assert resultado.blocos == []
