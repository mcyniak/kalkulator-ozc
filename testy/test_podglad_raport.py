"""Wycinki skanu, raport Word, pola do uzupełnienia, druga warstwa muru."""
import io
from datetime import datetime

import pytest
from docx import Document
from PIL import Image

from ozc import przegrody
from ozc.dane import Dane, Miejsce
from ozc.obliczenia import oblicz, pola_do_uzupelnienia
from ozc.podglad import strony, wycinek
from ozc.raport_word import nazwa_pliku, utworz_raport

from .test_obliczenia import prosty_budynek


def _png(w=1000, h=1400) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(b, format="PNG")
    return b.getvalue()


def test_wycinek_obejmuje_wskazane_miejsce_z_marginesem():
    strona = strony([("s1.png", _png())])[0]
    kawalek = wycinek(strona, Miejsce(1, (400, 500, 450, 510)))
    w, h = kawalek.size
    assert w >= 0.35 * 1000 - 1 and h >= 0.10 * 1400 - 1   # minimalny kontekst
    assert w < 1000 and h < 1400                             # ale nie cała strona
    assert (220, 0, 0) in {kolor for _, kolor in kawalek.getcolors(10**7)}   # czerwona ramka


def test_wycinek_przy_krawedzi_nie_wychodzi_poza_strone():
    strona = strony([("s1.png", _png())])[0]
    kawalek = wycinek(strona, Miejsce(1, (0, 0, 20, 10)))
    assert kawalek.size[0] <= 1000 and kawalek.size[1] <= 1400


def test_nazwa_pliku_jak_w_dotychczasowych_raportach():
    assert nazwa_pliku("Przykładowa 1, 00-001 Testowo", datetime(2026, 7, 3, 14, 55, 19)) == \
        "OZC_Przykładowa 1 00-001 Testowo_20260703_145519"
    assert "/" not in nazwa_pliku('Zła/nazwa: "x"', datetime(2026, 1, 1))


def test_raport_word_zawiera_adres_wynik_i_wykresy(tmp_path):
    d = prosty_budynek(adres="Przykładowa 1, 00-001 Testowo", wlasciciel="Jan Testowy", gmina="Testowo")
    w = oblicz(d)
    docx, pdf = utworz_raport(d, w, tmp_path, datetime(2026, 7, 3, 14, 55, 19), pdf=False)
    assert docx.name == "OZC_Przykładowa 1 00-001 Testowo_20260703_145519.docx" and pdf is None
    doc = Document(docx)
    tekst = "\n".join(p.text for p in doc.paragraphs)
    komorki = [c.text for t in doc.tables for r in t.rows for c in r.cells]
    assert "BILANS CIEPLNY BUDYNKU" in tekst
    assert "Przykładowa 1, 00-001 Testowo" in komorki and "Jan Testowy" in komorki
    assert any(f"{w.phi_HL:.0f} W" in c for c in komorki)
    assert len(doc.inline_shapes) == 2  # dwa wykresy kołowe


def test_druga_warstwa_muru():
    jedna = przegrody.u_sciany("Bloczek betonowy", 24, "Styropian EPS", 6)
    dwie = przegrody.u_sciany("Bloczek betonowy", 24, "Styropian EPS", 6, "Cegła ceramiczna pełna", 12)
    assert dwie == pytest.approx(1 / (1 / jedna + 0.12 / 0.77))


def test_pola_do_uzupelnienia_bez_okien_i_drzwi():
    d = prosty_budynek(okna_srednie=None, drzwi_ilosc=None)
    braki = pola_do_uzupelnienia(d)
    assert {"okna_male", "okna_srednie", "okna_duze", "drzwi_ilosc"} <= set(braki)
    assert pola_do_uzupelnienia(prosty_budynek()) == []


def test_pola_do_uzupelnienia_nie_rusza_oryginalu():
    d = Dane({"strefa": "II"})
    pola_do_uzupelnienia(d)
    assert "piwnica" not in d.wartosci
