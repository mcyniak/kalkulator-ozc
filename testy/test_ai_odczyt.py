"""Moduł AI — bez połączenia z API (sztuczny klient)."""
import json
from types import SimpleNamespace

import pytest

from ozc import ai_odczyt
from ozc.ai_odczyt import SCHEMAT, SYSTEM, BladOdczytu, odczytaj_audyt, przetworz_odpowiedz
from ozc.dane import Miejsce

ODPOWIEDZ = {
    "pola": [
        {"klucz": "strefa", "wartosc": "II", "zrodlo": "AI – do sprawdzenia", "uwaga": "pow. łowicki",
         "strona": 1, "obszar": [100, 80, 600, 120]},
        {"klucz": "h_parter", "wartosc": "2,6", "zrodlo": "protokół", "uwaga": "",
         "strona": 1, "obszar": [0, 0, 0, 0]},
        {"klucz": "sciana_material", "wartosc": "Pustak żelbetowy", "zrodlo": "protokół – odczyt niepewny",
         "uwaga": "", "strona": 1, "obszar": [50, 700, 500, 720]},
    ],
    "pytania": [{"tekst": "Ile jest okien?", "klucze": ["okna_srednie"], "strona": 3, "obszar": [500, 600, 990, 950]}],
    "podsumowanie": "Dom parterowy z poddaszem.",
}


class SztucznyKlient:
    def __init__(self, tekst: str, stop_reason: str = "end_turn"):
        self.wywolania = []
        odp = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=tekst)])

        def create(**kw):
            self.wywolania.append(kw)
            return odp

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_przetworz_odpowiedz():
    w = przetworz_odpowiedz(ODPOWIEDZ)
    assert w.dane.get("strefa") == "II" and w.dane.zrodla["strefa"] == "AI – do sprawdzenia"
    assert w.dane.miejsca["strefa"] == Miejsce(1, (100, 80, 600, 120))
    assert w.dane.get("h_parter") == 2.6
    assert "h_parter" not in w.dane.miejsca  # [0,0,0,0] = miejsce nieznane
    assert w.dane.zrodla["h_kolanka"] == "założenie domyślne"


def test_wartosc_spoza_listy_trafia_do_pytan_z_miejscem():
    w = przetworz_odpowiedz(ODPOWIEDZ)
    assert w.dane.get("sciana_material") is None
    pyt = next(p for p in w.pytania if "Pustak żelbetowy" in p.tekst)
    assert pyt.klucze == ["sciana_material"] and pyt.miejsce.strona == 1


def test_pytania_z_kluczami_i_miejscem():
    pyt = next(p for p in przetworz_odpowiedz(ODPOWIEDZ).pytania if p.tekst == "Ile jest okien?")
    assert pyt.klucze == ["okna_srednie"] and pyt.miejsce == Miejsce(3, (500, 600, 990, 950))


@pytest.mark.parametrize("strona, obszar", [(0, [1, 2, 3, 4]), (1, [5, 5, 5, 9]), (2, [1, 2, 3])])
def test_niepoprawne_miejsce_jest_pomijane(strona, obszar):
    assert ai_odczyt._miejsce({"strona": strona, "obszar": obszar}) is None


def test_miejsce_przycinane_do_strony():
    assert ai_odczyt._miejsce({"strona": 1, "obszar": [-20, 10, 1200, 50]}) == Miejsce(1, (0, 10, 1000, 50))


def test_wywolanie_api_i_parsowanie():
    klient = SztucznyKlient(json.dumps(ODPOWIEDZ))
    w = odczytaj_audyt([("audyt.pdf", b"%PDF-1.4")], client=klient)
    assert w.podsumowanie == "Dom parterowy z poddaszem."
    kw = klient.wywolania[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"]["schema"] is SCHEMAT
    blok = kw["messages"][0]["content"][0]
    assert blok["type"] == "document" and blok["source"]["media_type"] == "application/pdf"


def test_odmowa_i_ucieta_odpowiedz():
    with pytest.raises(BladOdczytu):
        odczytaj_audyt([("a.pdf", b"x")], client=SztucznyKlient("", stop_reason="refusal"))
    with pytest.raises(BladOdczytu):
        odczytaj_audyt([("a.pdf", b"x")], client=SztucznyKlient("{", stop_reason="max_tokens"))


def test_nieobslugiwany_plik():
    with pytest.raises(BladOdczytu):
        odczytaj_audyt([("a.docx", b"x")], client=SztucznyKlient("{}"))


def test_katalog_pol_w_promptcie():
    assert "`h_kolanka`" in SYSTEM and "`sciana_material_2`" in SYSTEM and "`wlasciciel`" in SYSTEM
    assert "t_int" not in SCHEMAT["properties"]["pola"]["items"]["properties"]["klucz"]["enum"]
    assert "t_int" in ai_odczyt.POMIJANE
