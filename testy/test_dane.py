"""Normalizacja danych i odczyt szablonu Excel."""
from pathlib import Path

import pytest

from ozc.dane import Dane, normalizuj, normalizuj_wartosc, uzupelnij_domyslne, wczytaj_xlsx
from ozc.pola import POLA_WEJSCIOWE
from ozc.szablon import zbuduj_skoroszyt


def test_liczby_z_przecinkiem_i_listy_bez_wielkosci_liter():
    assert normalizuj_wartosc(POLA_WEJSCIOWE["h_parter"], "2,6") == 2.6
    assert normalizuj_wartosc(POLA_WEJSCIOWE["okna_male"], "4") == 4
    assert normalizuj_wartosc(POLA_WEJSCIOWE["strefa"], "ii") == "II"
    assert normalizuj_wartosc(POLA_WEJSCIOWE["h_parter"], "  ") is None


@pytest.mark.parametrize("klucz, wartosc", [("h_parter", "abc"), ("h_parter", "12"), ("strefa", "VI")])
def test_bledne_wartosci(klucz, wartosc):
    with pytest.raises(ValueError):
        normalizuj_wartosc(POLA_WEJSCIOWE[klucz], wartosc)


def test_normalizuj_zbiera_problemy_zamiast_przerywac():
    d, problemy = normalizuj(Dane({"h_parter": "dużo", "strefa": "II"}))
    assert d.get("h_parter") is None and d.get("strefa") == "II"
    assert len(problemy) == 1


def test_domyslne_sa_oznaczone():
    d = uzupelnij_domyslne(Dane({"h_kolanka": 1.4}))
    assert d.get("h_kolanka") == 1.4 and "h_kolanka" not in d.zrodla
    assert d.get("t_int") == 20.0 and d.zrodla["t_int"] == "założenie domyślne"


def test_excel_tam_i_z_powrotem(tmp_path: Path):
    wejscie = {"wartosci": {"strefa": "II", "h_parter": 2.6, "sciana_material": "Beton"},
               "zrodla": {"strefa": "AI – do sprawdzenia"}, "uwagi": {"h_parter": "sprawdzić"}}
    plik = tmp_path / "a.xlsx"
    zbuduj_skoroszyt(wejscie).save(plik)
    d = wczytaj_xlsx(plik)
    assert d.get("strefa") == "II" and d.get("h_parter") == 2.6 and d.get("sciana_material") == "Beton"
    assert d.zrodla["strefa"] == "AI – do sprawdzenia"
    assert d.uwagi["h_parter"] == "sprawdzić"
    assert d.zrodla["t_int"] == "założenie domyślne"
