"""Import komputerowych audytów FlexiPower — na tekście w formacie PDF-a (dane fikcyjne)."""
from pathlib import Path

import pytest

from ozc.dane import normalizuj
from ozc.import_flexipower import _okna_w_kategorie, interpretuj, oczysc, parsuj_tekst
from ozc.obliczenia import oblicz, pola_do_uzupelnienia, zalozenia_kluczowe

TEKST = oczysc((Path(__file__).parent / "dane" / "audyt_flexipower.txt").read_text(encoding="utf-8"))


@pytest.fixture
def wynik():
    return interpretuj(parsuj_tekst(TEKST))


def test_parsowanie_surowe():
    r = parsuj_tekst(TEKST)
    assert r["adres"] == "Lipowa 7, 00-001 Przykładowo" and r["pow"] == 160 and r["rok"] == 2004
    assert [m for m, _ in r["przegrody"]["Ściana zewnętrzna"]] == [
        "Tynk cementowo-wapienny", "Cegła dziurawka", "Styropian", "Cegła dziurawka"]
    assert len(r["elewacje"]) == 4
    assert r["elewacje"][1]["drzwi"][1] == {"typ": "balkonowe_tarasowe", "pow": 4.0, "U": (0.9, 0.9)}


def test_odczyt_wprost_i_wyliczenia(wynik):
    d = wynik.dane
    assert d.get("wlasciciel") == "Jan Testowy" and d.zrodla["adres"] == "protokół"
    # U ściany z warstw: 1 / (0,17 + 0,02/0,82 + 0,36/0,62 + 0,04/0,04)
    assert d.get("sciana_U_reczne") == pytest.approx(1 / (0.17 + 0.02 / 0.82 + 0.36 / 0.62 + 1.0), abs=1e-3)
    assert d.zrodla["sciana_U_reczne"] == "przeliczone z audytu"  # jednoznaczne — bez potwierdzania
    assert d.zrodla["liczba_pieter"] == "wyliczone z audytu"      # szacunek z wysokości ścian — do potwierdzenia
    assert d.get("dl_budynku") == 11 and d.get("szer_budynku") == 10
    assert d.get("liczba_pieter") == 1 and "wysokości ścian" in d.uwagi["liczba_pieter"]  # 5,6 m → 2 kondygnacje
    assert d.get("kat_dachu") == pytest.approx(31, abs=1)  # atan(2,9 / 5)


def test_okna_drzwi_i_bramy(wynik):
    d = wynik.dane
    # okna 6 + 1,5 + 0,8 oraz drzwi balkonowe 4 m² (liczone jak okno); brama garażowa pominięta
    pow_okien = sum(d.get(f"okna_{k}", 0) * d.get(f"pow_okna_{k}", 0) for k in ("male", "srednie", "duze"))
    assert pow_okien == pytest.approx(6 + 1.5 + 0.8 + 4)
    assert d.get("drzwi_ilosc") == 1 and d.get("drzwi_szer") * d.get("drzwi_wys") == pytest.approx(2.0)
    assert d.get("drzwi_U_reczne") is None and d.get("drzwi_rok") == 2004  # „nie_znam” → typowe dla roku
    assert any("bram" in p.tekst for p in wynik.pytania)


def test_strop_bez_izolacji_jest_do_potwierdzenia(wynik):
    d = wynik.dane
    assert d.get("strop_konstrukcja") == "Żelbetowy monolityczny" and d.get("strop_grubosc") == 9
    assert d.get("strop_U_reczne") is None
    assert "strop_izolacja_grubosc" in zalozenia_kluczowe(d)
    assert any("izolacji stropu" in p.tekst for p in wynik.pytania)


def test_po_wybraniu_strefy_da_sie_policzyc(wynik):
    d, problemy = normalizuj(wynik.dane)
    assert problemy == []
    assert pola_do_uzupelnienia(d) == ["strefa"]
    d.wartosci["strefa"] = "II"
    w = oblicz(d)
    assert 5 < w.phi_HL_kW < 15


def test_duze_przeszklenia_dzielone_na_okna_w_zakresie_pola():
    k = _okna_w_kategorie([0.6, 1.4, 14.0])
    assert k["okna_male"] == 1 and k["okna_srednie"] == 1 and k["okna_duze"] == 3
    assert 1.5 <= k["pow_okna_duze"] <= 8


# --- regresje z przeglądu kodu ---------------------------------------------------------------

def _z_podmiana(stary, nowy):
    assert stary in TEKST
    return interpretuj(parsuj_tekst(TEKST.replace(stary, nowy)))


@pytest.mark.parametrize("tekst, oczekiwane", [
    ("Ud ≤ 1,3 (2010 r.)", (1.3, 1.3)),
    ("Uw = 1,1 W/m2K", (1.1, 1.1)),
    ("Uw = 0,9–1,1", (0.9, 1.1)),
    ("nie_znam", None),
])
def test_u_bez_lat_i_jednostek(tekst, oczekiwane):
    from ozc.import_flexipower import _zakres_u
    assert _zakres_u(tekst) == oczekiwane


def test_krotki_odcinek_sciany_nie_jest_szerokoscia_budynku():
    ganek = "Ściana elewacyjna nr 4:\n Kształt: prostokąt\n szerokość: 2.5\n wysokość: 3\nŚciana elewacyjna nr 5:"
    w = _z_podmiana("Ściana elewacyjna nr 4:", ganek)
    assert w.dane.get("szer_budynku") == 10  # podstawa ściany szczytowej, nie 2,5 m ganku


def test_okno_bez_powierzchni_nie_znika():
    w = _z_podmiana(" Okno 1: powierzchnia: 0.8, izolacja: Uw = 0,9–1,1", " Okno 1: izolacja: Uw = 0,9–1,1")
    d = w.dane
    pow_okien = sum(d.get(f"okna_{k}", 0) * d.get(f"pow_okna_{k}", 0) for k in ("male", "srednie", "duze"))
    assert pow_okien == pytest.approx(6 + 1.5 + 4 + 1.8)  # 0,8 m² zastąpione typowym oknem 1,8 m²
    assert d.zrodla["okna_srednie"] == "wyliczone z audytu"
    assert any("nie ma powierzchni" in p.tekst for p in w.pytania)


def test_parterowy_z_ocieplonym_sufitem_nie_dostaje_poddasza():
    t = TEKST.replace("unheated ceiling:\n Warstwa 1: Żelbet (U = 1,70 W/(m·K)) — grubość 9 cm",
                      "Strop / sufit ogrzewany:\n Warstwa 1: Żelbet (U = 1,70 W/(m·K)) — grubość 9 cm\n"
                      " Warstwa 2: Wełna mineralna — grubość 20 cm")
    t = t.replace("Rok budowy 2004", "Rok budowy 2004\nLiczba kondygnacji ogrzewanych 1")
    d = interpretuj(parsuj_tekst(t)).dane
    assert d.get("poddasze_uzytkowe") == "Nie" and d.get("liczba_pieter") == 0
    assert d.get("strop_U_reczne") is not None and d.get("dach_U_reczne") is None


def test_nieznane_warstwy_podlogi_daja_pytanie():
    w = _z_podmiana(" Warstwa 1: Wylewka betonowa — grubość 8 cm\n Warstwa 2: Styropian — grubość 10 cm",
                    " Warstwa 1: Panele — grubość 1 cm\n Warstwa 2: — — grubość 10 cm")
    assert w.dane.zrodla["podloga_U_reczne"] == "wyliczone z audytu"
    assert any("Podłoga" in p.tekst and "Panele" in p.tekst and "izolację" in p.tekst for p in w.pytania)


def test_kolejne_naglowki_stron_usuwane():
    assert oczysc("a\nFLEXIPOWER GROUP\nDOKUMENTACJA POWYKONAWCZA\nb") == "a\nb"


def test_same_okna_bez_powierzchni_to_pytanie_do_czlowieka():
    t = TEKST
    for linia in [l for l in t.splitlines() if "Okno" in l or "Drzwi" in l]:
        t = t.replace(linia + "\n", "")
    t = t.replace("Ściana elewacyjna nr 1:\n", "Ściana elewacyjna nr 1:\n Okno 1: izolacja: Uw = 0,8–0,9\n", 1)
    w = interpretuj(parsuj_tekst(t))
    assert w.dane.get("okna_srednie") is None  # nie zgadujemy liczby okien
    assert any("1 okien, ale bez powierzchni" in p.tekst for p in w.pytania)
    assert "1 okien/drzwi balkonowych (w tym 1 bez powierzchni)" in w.podsumowanie


def test_po_wpisaniu_liczby_drzwi_wymiary_i_rok_sa_zakladane():
    t = "\n".join(l for l in TEKST.splitlines() if "Drzwi" not in l)
    d, _ = normalizuj(interpretuj(parsuj_tekst(t)).dane)
    assert "drzwi_ilosc" in pola_do_uzupelnienia(d)
    d.wartosci.update(strefa="II", drzwi_ilosc=1)
    assert pola_do_uzupelnienia(d) == []
    assert any("Rok montażu" in z for z in oblicz(d).zalozenia)


def test_welna_szklana_w_stropie_to_izolacja():
    t = TEKST.replace("unheated ceiling:\n Warstwa 1: Żelbet (U = 1,70 W/(m·K)) — grubość 9 cm",
                      "unheated ceiling:\n Warstwa 1: Drewno — grubość 2.5 cm\n Warstwa 2: Wełna szklana — grubość 30 cm")
    d = interpretuj(parsuj_tekst(t)).dane
    assert d.get("strop_U_reczne") == pytest.approx(1 / (0.1 + 0.04 + 0.025 / 0.16 + 0.30 / 0.040), abs=0.01)
