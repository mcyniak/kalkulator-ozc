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


def test_zatwierdz_zapisuje_i_przechodzi_do_nastepnego(tmp_path, monkeypatch):
    from pathlib import Path

    from ozc import konfiguracja, raport_word
    from ozc.dane import normalizuj
    from ozc.import_flexipower import interpretuj, oczysc, parsuj_tekst
    from ozc.obliczenia import oblicz

    monkeypatch.delenv(klucz_api.ZMIENNA, raising=False)
    monkeypatch.setattr(klucz_api, "PLIK_KLUCZA", tmp_path / "klucz_api.txt")
    monkeypatch.setattr(konfiguracja, "KATALOG_DANYCH", tmp_path)
    monkeypatch.setattr(raport_word, "docx_na_pdf", lambda docx, pdf: False)  # bez Worda w testach
    tekst = oczysc((Path(__file__).parent / "dane" / "audyt_flexipower.txt").read_text(encoding="utf-8"))

    def audyt(nr):
        d, _ = normalizuj(interpretuj(parsuj_tekst(tekst)).dane)
        d.wartosci["strefa"] = "II"
        d.wartosci["adres"] = f"Lipowa {nr}, 00-001 Przykładowo"
        return {"id": f"a{nr}", "nazwa": f"a{nr}.pdf", "pliki": [], "dane": d, "pytania": [], "podsumowanie": "",
                "wynik": oblicz(d), "blad": None, "zapisano": None}

    at = AppTest.from_file(str(KATALOG_PROJEKTU / "app.py"), default_timeout=60)
    at.session_state["audyty"] = [audyt(1), audyt(2)]
    at.run()
    next(b for b in at.button if b.label.startswith("✅ Zatwierdź")).click().run()
    assert not at.exception
    audyty = at.session_state["audyty"]
    assert audyty[0]["zapisano"] and not audyty[1]["zapisano"]
    assert at.session_state["wybrany_audyt"] == 1          # przeszedł do następnego
    assert any("Zapisano: Lipowa 1" in s.value for s in at.success)
    assert list((tmp_path / "adresy").glob("*/OZC_*.docx"))
