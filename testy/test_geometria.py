"""Geometria z obrysu — przypadki policzone ręcznie."""
import math

import pytest

from ozc.dane import Dane
from ozc.geometria import oblicz_geometrie
from ozc.konfiguracja import wczytaj_konfiguracje

CFG = wczytaj_konfiguracje()
D_ST = CFG["geometria"]["grubosc_stropu"]


def dane(**kw) -> Dane:
    baza = dict(obrys="Prostokąt", dl_budynku=10.0, szer_budynku=8.0, sciana_grubosc=30.0,
                sciana_ocieplenie_grubosc=0.0, h_parter=2.5, piwnica="Brak", liczba_pieter=0,
                poddasze_uzytkowe="Nie", dach_rodzaj="Płaski", typ_zabudowy="Wolnostojący")
    baza.update(kw)
    return Dane(baza)


def test_parterowy_z_dachem_plaskim():
    g = oblicz_geometrie(dane(), CFG)
    t = 0.33
    assert g.grubosc_scian == pytest.approx(t)
    assert g.sciany_brutto == pytest.approx(36 * (2.5 + D_ST))
    assert g.stropodach == pytest.approx(80)
    assert g.podloga_grunt == pytest.approx((10 - 2 * t) * (8 - 2 * t))
    assert g.kubatura == pytest.approx((10 - 2 * t) * (8 - 2 * t) * 2.5)
    assert g.obwod_wewn_eksponowany == pytest.approx(2 * (10 - 2 * t + 8 - 2 * t))


def test_poddasze_dwuspadowe_ze_strychem():
    g = oblicz_geometrie(dane(poddasze_uzytkowe="Tak", dach_rodzaj="Skośny dwuspadowy", kat_dachu=45.0,
                              h_poddasza=2.5, h_kolanka=1.0, strych_nieogrzewany="Tak"), CFG)
    # x = (2,5 − 1,0)/tg45 = 1,5; pas stropu = 8 − 3 = 5
    assert g.strop_strych == pytest.approx(10 * 5)
    assert g.dach_skos == pytest.approx(2 * 10 * 1.5 / math.cos(math.radians(45)))
    szczyt = 8 * 1.0 + (8 + 5) / 2 * 1.5
    assert g.sciany_brutto == pytest.approx(36 * (2.5 + D_ST) + 2 * 10 * 1.0 + 2 * szczyt)


def test_poddasze_bez_strychu_skos_do_kalenicy():
    g = oblicz_geometrie(dane(poddasze_uzytkowe="Tak", dach_rodzaj="Skośny dwuspadowy", kat_dachu=45.0,
                              h_poddasza=2.5, h_kolanka=1.0, strych_nieogrzewany="Nie"), CFG)
    assert g.strop_strych == 0
    assert g.dach_skos == pytest.approx(10 * 8 / math.cos(math.radians(45)))
    szczyt = 8 * 1.0 + 8 * 8 * 1.0 / 4
    assert g.sciany_brutto == pytest.approx(36 * (2.5 + D_ST) + 2 * 10 * 1.0 + 2 * szczyt)


def test_dach_skosny_bez_poddasza_to_strop_pod_strychem():
    g = oblicz_geometrie(dane(dach_rodzaj="Skośny dwuspadowy"), CFG)
    assert g.strop_strych == pytest.approx(80)
    assert g.dach_skos == 0


def test_blizniak_przenosi_sciane_do_sasiada():
    g = oblicz_geometrie(dane(typ_zabudowy="Bliźniak", dl_sciany_wspolnej=8.0), CFG)
    assert g.obwod_zewn == pytest.approx(36 - 8)
    assert g.sciany_sasiad == pytest.approx(8 * (2.5 + D_ST))


def test_piwnica_nieogrzewana_daje_strop_zamiast_podlogi():
    g = oblicz_geometrie(dane(piwnica="Nieogrzewana"), CFG)
    assert g.podloga_grunt == 0
    assert g.strop_piwnica == pytest.approx(g.pole_wewn)


def test_obrys_nieprostokatny():
    g = oblicz_geometrie(dane(obrys="Inny (podaj pole i obwód)", pole_zabudowy=80.0, obwod=36.0), CFG)
    assert {round(g.dlugosc, 6), round(g.szerokosc, 6)} == {10.0, 8.0}


def test_powierzchnia_poddasza_wg_9836():
    # strop na 2,5 m, kolanko 1,0, 45°: pełna wys. 2,2 od 1,2 m od ściany, 1,4 od 0,4 m
    g = oblicz_geometrie(dane(poddasze_uzytkowe="Tak", dach_rodzaj="Skośny dwuspadowy",
                              kat_dachu=45.0, h_poddasza=2.5, h_kolanka=1.0, strych_nieogrzewany="Tak"), CFG)
    w = 8 - 2 * 0.33
    l = 10 - 2 * 0.33
    oczekiwane = l * (w - 2.4) + 0.5 * l * ((w - 0.8) - (w - 2.4))
    assert g.kondygnacje[-1][1] == pytest.approx(oczekiwane)
