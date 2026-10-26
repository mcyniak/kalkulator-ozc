"""Aplikacja Streamlit uruchamiana bez przeglądarki (AppTest) — każda strona renderuje się bez błędów."""
import pytest
from streamlit.testing.v1 import AppTest

from ozc import klucz_api
from ozc.konfiguracja import KATALOG_PROJEKTU


@pytest.fixture
def aplikacja(tmp_path, monkeypatch):
    monkeypatch.delenv(klucz_api.ZMIENNA, raising=False)
    monkeypatch.setattr(klucz_api, "PLIK_KLUCZA", tmp_path / "klucz_api.txt")
    at = AppTest.from_file(str(KATALOG_PROJEKTU / "app.py"), default_timeout=60)
    at.run()
    return at


@pytest.mark.parametrize("strona", ["Audyty", "Lista adresów", "Ustawienia"])
def test_strony_bez_bledow(aplikacja, strona):
    aplikacja.sidebar.radio[0].set_value(strona).run()
    assert not aplikacja.exception
    assert aplikacja.title[0].value == strona


def test_brak_klucza_jest_widoczny(aplikacja):
    assert any("Brak klucza API" in w.value for w in aplikacja.sidebar.warning)
