import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(RAIZ))

import pytest


def ler_fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


@pytest.fixture
def pagina_completa() -> str:
    """Página real de 11/09/2026, com desjejum, almoço e jantar."""
    return ler_fixture("pagina-completa.html")


@pytest.fixture
def pagina_vazia() -> str:
    """Página íntegra que diz explicitamente não haver cardápio."""
    return ler_fixture("pagina-vazia.html")


@pytest.fixture
def pagina_quebrada() -> str:
    """Página com conteúdo institucional e nenhum cabeçalho reconhecível."""
    return ler_fixture("pagina-quebrada.html")


@pytest.fixture
def pagina_servida(monkeypatch):
    """Faz `baixar` devolver o HTML escolhido, sem tocar na rede."""

    def servir(html: str):
        import ru_bot

        monkeypatch.setattr(ru_bot, "baixar", lambda dia=None: html)

    return servir
