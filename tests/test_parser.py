"""Regressão do parser contra a página real congelada em tests/fixtures."""

import ru_bot


def test_reconhece_as_tres_refeicoes(pagina_completa):
    blocos = ru_bot.parsear(pagina_completa)
    assert [b["refeicao"] for b in blocos] == ["Desjejum", "Almoço", "Jantar"]


def test_campus_e_data_do_cabecalho(pagina_completa):
    almoco = ru_bot.parsear(pagina_completa)[1]
    assert almoco["campus"] == "Alegre e Jerônimo Monteiro"
    assert almoco["data"] == "sexta-feira, 11 de Setembro de 2026"


def test_secoes_do_almoco(pagina_completa):
    almoco = ru_bot.parsear(pagina_completa)[1]
    rotulos = [categoria for categoria, _ in almoco["secoes"]]
    assert rotulos == [
        "Entrada", "Prato Proteico", "Opção",
        "Acompanhamento", "Guarnição", "Sobremesa", "Suco",
    ]
    itens = dict(almoco["secoes"])
    assert itens["Prato Proteico"] == ["Peixe Frito"]
    assert len(itens["Entrada"]) == 2


def test_rodape_nao_vira_item(pagina_completa):
    """As notas de rodapé encerram o bloco em vez de entrar na última seção."""
    blocos = ru_bot.parsear(pagina_completa)
    todos_os_itens = [
        item for b in blocos for _, itens in b["secoes"] for item in itens
    ]
    assert not any("traços de glúten" in i for i in todos_os_itens)
    assert not any(i.startswith("CG =") for i in todos_os_itens)


def test_filtro_por_campus_e_refeicao(pagina_completa):
    blocos = ru_bot.parsear(pagina_completa)
    so_almoco = ru_bot.filtrar(blocos, ["almoco"], "alegre")
    assert len(so_almoco) == 1
    assert so_almoco[0]["refeicao"] == "Almoço"


def test_formatacao_escapa_html(pagina_completa):
    blocos = ru_bot.filtrar(ru_bot.parsear(pagina_completa), ["almoco"], "alegre")
    msg = ru_bot.formatar(blocos, "https://exemplo/cardapio")
    assert "<b>Almoço</b>" in msg
    assert "• Peixe Frito" in msg
    assert msg.endswith('<a href="https://exemplo/cardapio">ver no site</a>')
