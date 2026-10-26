"""Moduł AI — bez połączenia z API (sztuczny klient)."""
import json
from types import SimpleNamespace

import pytest

from ozc import ai_odczyt
from ozc.ai_odczyt import SCHEMAT, SYSTEM, BladOdczytu, odczytaj_audyt, przetworz_odpowiedz

ODPOWIEDZ = {
    "pola": [
        {"klucz": "strefa", "wartosc": "II", "zrodlo": "AI – do sprawdzenia", "uwaga": "pow. łowicki"},
        {"klucz": "h_parter", "wartosc": "2,6", "zrodlo": "protokół", "uwaga": ""},
        {"klucz": "sciana_material", "wartosc": "Pustak żelbetowy", "zrodlo": "protokół – odczyt niepewny", "uwaga": ""},
    ],
    "pytania": ["Jaka jest wysokość ścianki kolankowej?"],
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
    assert w.dane.get("h_parter") == 2.6
    assert w.dane.get("sciana_material") is None  # spoza listy → nie trafia do obliczeń…
    assert any("Pustak żelbetowy" in p for p in w.pytania)  # …tylko do pytań
    assert w.dane.zrodla["h_kolanka"] == "założenie domyślne"


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
    assert "`h_kolanka`" in SYSTEM and "Pustak keramzytobetonowy" in SYSTEM
    assert "t_int" not in SCHEMAT["properties"]["pola"]["items"]["properties"]["klucz"]["enum"]
    assert "t_int" in ai_odczyt.POMIJANE
