"""Obliczenie Φ_HL — prosty budynek policzony ręcznie + przykład protokołu 24."""
import tomllib
from pathlib import Path

import pytest

from ozc import grunt
from ozc.dane import BladDanych, Dane, normalizuj, wczytaj_xlsx
from ozc.konfiguracja import KATALOG_PROJEKTU, wczytaj_konfiguracje
from ozc.obliczenia import oblicz
from ozc.szablon import zbuduj_skoroszyt

CFG = wczytaj_konfiguracje()
N = CFG["norma"]


def prosty_budynek(**kw) -> Dane:
    """Parterowy 10 × 8 m, dach płaski, U wpisane ręcznie — łatwy do sprawdzenia na kartce."""
    w = dict(strefa="III", t_int=20.0, obrys="Prostokąt", dl_budynku=10.0, szer_budynku=8.0,
             sciana_grubosc=30.0, sciana_ocieplenie_grubosc=0.0, sciana_U_reczne=0.3,
             h_parter=2.5, piwnica="Brak", liczba_pieter=0, poddasze_uzytkowe="Nie", dach_rodzaj="Płaski",
             strop_U_reczne=0.2, podloga_U_reczne=0.3, okna_srednie=4, pow_okna_srednie=1.5, okna_U_reczne=1.5,
             drzwi_ilosc=1, drzwi_szer=1.0, drzwi_wys=2.0, drzwi_U_reczne=2.0,
             wentylacja="Grawitacyjna", szczelnosc="Średni", oslonienie="Średnie",
             typ_zabudowy="Wolnostojący", woda_gruntowa_plytko="Nie")
    w.update(kw)
    return Dane(w)


def test_prosty_budynek_recznie():
    w = oblicz(prosty_budynek())
    dT = 20 - (-20)
    dU = N["delta_U_tb"]
    t = 0.33
    sciany = 36 * (2.5 + CFG["geometria"]["grubosc_stropu"]) - 6.0 - 2.0
    dok = N["dodatek_U_okna_drzwi"]  # U okien/drzwi wpisane ręcznie = katalogowe → + dodatek na osadzenie
    phi_przegrody = (sciany * (0.3 + dU) + 6.0 * (1.5 + dok + dU) + 2.0 * (2.0 + dok + dU) + 80 * (0.2 + dU)) * dT

    a, p = (10 - 2 * t) * (8 - 2 * t), 2 * (10 - 2 * t + 8 - 2 * t)
    u_eq = grunt.u_plyty_na_gruncie(a / (0.5 * p), t, 0.3)
    fg2 = (20 - 7.6) / dT
    phi_grunt = 1.45 * fg2 * a * u_eq * 1.0 * dT

    V = a * 2.5
    v = max(N["wsp_infiltracji_budynek"] * 2 * V * 7.0 * 0.03 * 1.0, N["n_min"] * V)
    phi_v = 0.34 * v * dT

    assert w.phi_T == pytest.approx(phi_przegrody + phi_grunt)
    assert w.phi_V == pytest.approx(phi_v)
    assert w.phi_HL == pytest.approx(phi_przegrody + phi_grunt + phi_v)
    assert sum(w.rozbicie().values()) == pytest.approx(w.phi_HL)


def test_kubatura_wentylacji_z_powierzchni_deklarowanej():
    pelna = oblicz(prosty_budynek())
    pol = oblicz(prosty_budynek(pow_ogrz_dekl=pelna.geometria.pow_ogrzewana / 2))
    assert pol.wentylacja["V"] == pytest.approx(pelna.geometria.kubatura / 2)
    assert pol.phi_V == pytest.approx(pelna.phi_V / 2)
    assert pol.phi_T == pytest.approx(pelna.phi_T)  # przegrody nadal z wymiarów


def test_odzysk_ciepla_zmniejsza_wentylacje():
    grawitacja = oblicz(prosty_budynek())
    odzysk = oblicz(prosty_budynek(wentylacja="Mechaniczna z odzyskiem", sprawnosc_odzysku=80.0))
    assert odzysk.phi_V < grawitacja.phi_V
    assert odzysk.phi_T == pytest.approx(grawitacja.phi_T)


def test_brak_danych_daje_czytelny_blad():
    with pytest.raises(BladDanych) as e:
        oblicz(prosty_budynek(strefa=None, h_parter=None))
    tekst = " ".join(e.value.problemy)
    assert "Strefa klimatyczna" in tekst and "Wysokość parteru" in tekst


def test_brak_U_przegrody_nie_daje_cichego_zera():
    with pytest.raises(BladDanych):
        oblicz(prosty_budynek(strop_U_reczne=None))


def test_dobor_pompy_z_blokadami():
    w = oblicz(prosty_budynek(liczba_osob=4), blokada_h=2)
    b = w.dobor
    assert b["phi_z_blokadami_kW"] == pytest.approx(w.phi_HL_kW * 24 / 22)
    assert b["wymagana_kW"] == pytest.approx(b["phi_z_blokadami_kW"] + 4 * 0.25)


def test_protokol_24(tmp_path: Path):
    przyklad = tomllib.loads((KATALOG_PROJEKTU / "przyklady" / "protokol_24.toml").read_text(encoding="utf-8"))
    plik = tmp_path / "p24.xlsx"
    zbuduj_skoroszyt(przyklad).save(plik)
    dane, problemy = normalizuj(wczytaj_xlsx(plik))
    assert problemy == []
    w = oblicz(dane)
    assert 10 < w.phi_HL_kW < 18
    assert any("różni się od deklarowanej" in o for o in w.ostrzezenia)
    assert any("Wysokość ścianki kolankowej" in z for z in w.zalozenia)


def test_wskazniki_na_tej_samej_podstawie_co_obliczenia():
    w = oblicz(prosty_budynek(pow_ogrz_dekl=100.0))
    assert w.pow_ogrzewana == 100.0 and w.kubatura == w.wentylacja["V"]
    assert f"{w.phi_HL / 100:.0f} W/m²" in "\n".join(w.kroki)
