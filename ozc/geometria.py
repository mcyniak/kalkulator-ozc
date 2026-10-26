"""Geometria budynku z obrysu: powierzchnie przegród, kubatura, powierzchnia ogrzewana.

Konwencja wymiarów:
  - ściany, dach, stropy — wymiary ZEWNĘTRZNE (obrys z protokołu),
  - podłoga na gruncie, kubatura, powierzchnia ogrzewana — wymiary WEWNĘTRZNE
    (obrys minus grubość ścian), zgodnie z PN-EN ISO 13370 dla gruntu.
Ścianki działowe pomijamy (kubatura nieco zawyżona — bezpieczniej).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .dane import Dane

TYNKI_M = 0.03  # łączna grubość tynków doliczana do grubości ściany


@dataclass
class Geometria:
    dlugosc: float
    szerokosc: float
    grubosc_scian: float
    obwod_zewn: float                 # bez ścian wspólnych z sąsiadem
    pole_wewn: float                  # rzut jednej kondygnacji w świetle ścian
    obwod_wewn_eksponowany: float     # obwód podłogi do gruntu (ISO 13370)
    sciany_brutto: float = 0.0        # ściany zewnętrzne z oknami i drzwiami
    sciany_sasiad: float = 0.0
    dach_skos: float = 0.0
    strop_strych: float = 0.0
    stropodach: float = 0.0
    podloga_grunt: float = 0.0
    strop_piwnica: float = 0.0
    piwnica_podloga: float = 0.0
    piwnica_sciany_grunt: float = 0.0
    piwnica_sciany_nad_terenem: float = 0.0
    piwnica_z: float = 0.0
    kubatura: float = 0.0
    pow_ogrzewana: float = 0.0
    wysokosc: float = 0.0             # od terenu do szczytu części ogrzewanej
    kondygnacje: list[tuple[str, float, float]] = field(default_factory=list)  # (nazwa, pole, kubatura)
    notatki: list[str] = field(default_factory=list)


def _prostokat_z_pola_i_obwodu(pole: float, obwod: float) -> tuple[float, float]:
    """Prostokąt zastępczy o tym samym polu i obwodzie (dla obrysu nieprostokątnego)."""
    s = obwod / 2
    delta = s * s - 4 * pole
    if delta < 0:
        bok = math.sqrt(pole)
        return bok, bok
    return (s + math.sqrt(delta)) / 2, (s - math.sqrt(delta)) / 2


def _szer_powyzej(h: float, h_kol: float, tg: float) -> float:
    """Odległość od ściany, w której skos osiąga wysokość h."""
    return max(0.0, (h - h_kol) / tg)


def _pole_wg_9836(dl: float, szer: float, h_kol: float, h_sufitu: float, tg: float, oba_kierunki: bool) -> float:
    """Powierzchnia poddasza wg PN-ISO 9836: 100% gdy h ≥ 2,2 m, 50% gdy 1,4–2,2 m."""
    def pole_powyzej(h: float) -> float:
        if h_sufitu < h:
            return 0.0
        s = _szer_powyzej(h, h_kol, tg)
        if oba_kierunki:
            return max(0.0, dl - 2 * s) * max(0.0, szer - 2 * s)
        return dl * max(0.0, szer - 2 * s)
    p22, p14 = pole_powyzej(2.2), pole_powyzej(1.4)
    return p22 + 0.5 * (p14 - p22)


def oblicz_geometrie(d: Dane, cfg: dict) -> Geometria:
    g = cfg["geometria"]
    d_st = g["grubosc_stropu"]
    notatki: list[str] = []

    if str(d.get("obrys", "Prostokąt")).startswith("Inny"):
        dl, sz = _prostokat_z_pola_i_obwodu(d.get("pole_zabudowy"), d.get("obwod"))
        notatki.append(f"Obrys nieprostokątny zastąpiono prostokątem {dl:.2f} × {sz:.2f} m "
                       "o tym samym polu i obwodzie.")
    else:
        dl, sz = d.get("dl_budynku"), d.get("szer_budynku")
    dl, sz = max(dl, sz), min(dl, sz)

    if d.get("sciana_grubosc"):
        t = (d.get("sciana_grubosc") + d.get("sciana_grubosc_2", 0) + d.get("sciana_ocieplenie_grubosc", 0)) / 100 + TYNKI_M
    else:
        t = g["grubosc_sciany_domyslna"]
        notatki.append(f"Brak grubości ściany — przyjęto {t:.2f} m do wymiarów wewnętrznych.")

    typ = d.get("typ_zabudowy", "Wolnostojący")
    n_wsp = {"Wolnostojący": 0, "Bliźniak": 1, "Szeregowiec skrajny": 1, "Szeregowiec środkowy": 2}[typ]
    l_wsp = d.get("dl_sciany_wspolnej", 0) if n_wsp else 0
    if n_wsp and not l_wsp:
        l_wsp = n_wsp * sz
        notatki.append(f"{typ}: brak długości ściany wspólnej — przyjęto {l_wsp:.2f} m "
                       "(krótszy bok budynku na każdą ścianę wspólną).")

    dl_w, sz_w = dl - 2 * t, sz - 2 * t
    geo = Geometria(
        dlugosc=dl, szerokosc=sz, grubosc_scian=t,
        obwod_zewn=2 * (dl + sz) - l_wsp,
        pole_wewn=dl_w * sz_w,
        obwod_wewn_eksponowany=2 * (dl_w + sz_w) - l_wsp,
        notatki=notatki,
    )

    def kondygnacja(nazwa: str, h: float) -> None:
        geo.sciany_brutto += geo.obwod_zewn * (h + d_st)
        geo.sciany_sasiad += l_wsp * (h + d_st)
        geo.kubatura += geo.pole_wewn * h
        geo.pow_ogrzewana += geo.pole_wewn
        geo.wysokosc += h + d_st
        geo.kondygnacje.append((nazwa, geo.pole_wewn, geo.pole_wewn * h))

    # --- piwnica ---
    piwnica = d.get("piwnica", "Brak")
    if piwnica == "Ogrzewana":
        h_p = d.get("h_piwnicy")
        nad = g["piwnica_nad_terenem"]
        z = max(0.0, h_p + d_st - nad)
        geo.piwnica_z = z
        geo.piwnica_podloga = geo.pole_wewn
        geo.piwnica_sciany_grunt = geo.obwod_wewn_eksponowany * z
        geo.piwnica_sciany_nad_terenem = geo.obwod_zewn * (h_p + d_st - z)
        geo.sciany_sasiad += l_wsp * (h_p + d_st)
        geo.kubatura += geo.pole_wewn * h_p
        geo.pow_ogrzewana += geo.pole_wewn
        geo.wysokosc += h_p + d_st - z
        geo.kondygnacje.append(("Piwnica", geo.pole_wewn, geo.pole_wewn * h_p))
        notatki.append(f"Piwnica ogrzewana: przyjęto {nad:.1f} m ściany ponad terenem, "
                       f"zagłębienie podłogi z = {z:.2f} m.")
    elif piwnica == "Nieogrzewana":
        geo.strop_piwnica = geo.pole_wewn
    else:
        geo.podloga_grunt = geo.pole_wewn

    # --- parter i piętra ---
    kondygnacja("Parter", d.get("h_parter"))
    for i in range(d.get("liczba_pieter", 0)):
        kondygnacja(f"Piętro {i + 1}", d.get("h_pietra"))

    # --- poddasze / dach ---
    dach = d.get("dach_rodzaj", "Skośny dwuspadowy")
    strych = d.get("strych_nieogrzewany", "Tak") == "Tak"
    if d.get("poddasze_uzytkowe") == "Tak":
        h_pod = d.get("h_poddasza")
        if dach == "Płaski":
            kondygnacja("Poddasze", h_pod)
            geo.stropodach = dl * sz
            notatki.append("Poddasze przy dachu płaskim policzono jak pełną kondygnację.")
        else:
            _poddasze(geo, d, dl, sz, t, l_wsp, n_wsp, strych, dach, notatki)
    elif dach == "Płaski":
        geo.stropodach = dl * sz
    else:
        geo.strop_strych = dl * sz
        if not strych:
            notatki.append("Dach skośny bez poddasza użytkowego — przyjęto nieogrzewany strych nad ostatnią kondygnacją.")
    return geo


def _poddasze(geo: Geometria, d: Dane, dl: float, sz: float, t: float, l_wsp: float, n_wsp: int,
              strych: bool, dach: str, notatki: list[str]) -> None:
    h_pod, h_kol = d.get("h_poddasza"), d.get("h_kolanka", 1.0)
    alfa = math.radians(d.get("kat_dachu"))
    tg, cos = math.tan(alfa), math.cos(alfa)
    wznios = h_pod - h_kol
    dl_w, sz_w = dl - 2 * t, sz - 2 * t
    MIN_STROP = 0.3  # węższy pas stropu traktujemy jak brak stropu

    if wznios <= 0:
        notatki.append("Ścianka kolankowa ≥ wysokość poddasza — poddasze policzono jak pełną kondygnację.")
        geo.sciany_brutto += geo.obwod_zewn * h_pod
        geo.sciany_sasiad += l_wsp * h_pod
        geo.strop_strych += dl * sz
        geo.kubatura += geo.pole_wewn * h_pod
        geo.pow_ogrzewana += geo.pole_wewn
        geo.wysokosc += h_pod
        geo.kondygnacje.append(("Poddasze", geo.pole_wewn, geo.pole_wewn * h_pod))
        return

    x = wznios / tg  # poziomy zasięg skosu od ściany do sufitu

    if dach == "Skośny dwuspadowy":
        wzdluz_dluzszego = d.get("kalenica", "Wzdłuż dłuższego boku") == "Wzdłuż dłuższego boku"
        le, w = (dl, sz) if wzdluz_dluzszego else (sz, dl)
        le_w, w_w = (dl_w, sz_w) if wzdluz_dluzszego else (sz_w, dl_w)
        pas = w - 2 * x
        if strych and pas > MIN_STROP:
            geo.strop_strych += le * pas
            geo.dach_skos += 2 * le * x / cos
            szczyt = w * h_kol + (w + pas) / 2 * wznios
            przekroj = w_w * h_pod - x * wznios
            h_sufitu = h_pod
        else:
            if strych:
                notatki.append("Przy tym kącie dachu i ściance kolankowej skos sięga kalenicy — brak stropu pod strychem.")
            geo.dach_skos += le * w / cos
            szczyt = w * h_kol + w * w * tg / 4
            przekroj = w_w * h_kol + w_w * w_w * tg / 4
            h_sufitu = h_kol + w_w / 2 * tg
        geo.sciany_brutto += 2 * le * h_kol + (2 - n_wsp) * szczyt
        geo.sciany_sasiad += n_wsp * szczyt
        objetosc = przekroj * le_w
        pole = _pole_wg_9836(le_w, w_w, h_kol, h_sufitu, tg, oba_kierunki=False)
        if n_wsp:
            notatki.append("Ściany wspólne z sąsiadem przyjęto jako ściany szczytowe poddasza.")
    else:  # wielospadowy
        pas_dl, pas_sz = dl - 2 * x, sz - 2 * x
        if strych and pas_dl > MIN_STROP and pas_sz > MIN_STROP:
            geo.strop_strych += pas_dl * pas_sz
            geo.dach_skos += (dl * sz - pas_dl * pas_sz) / cos
            gora = max(0.0, dl_w - 2 * x) * max(0.0, sz_w - 2 * x)
            objetosc = geo.pole_wewn * h_kol + (geo.pole_wewn + gora) / 2 * wznios
            h_sufitu = h_pod
        else:
            geo.dach_skos += dl * sz / cos
            h_kal = sz_w / 2 * tg
            objetosc = geo.pole_wewn * h_kol + geo.pole_wewn * h_kal / 3
            h_sufitu = h_kol + h_kal
        geo.sciany_brutto += geo.obwod_zewn * h_kol
        geo.sciany_sasiad += l_wsp * h_kol
        pole = _pole_wg_9836(dl_w, sz_w, h_kol, h_sufitu, tg, oba_kierunki=True)
        notatki.append("Dach wielospadowy — geometria poddasza przybliżona (bryła ścięta).")

    geo.kubatura += objetosc
    geo.pow_ogrzewana += pole
    geo.wysokosc += h_sufitu
    geo.kondygnacje.append(("Poddasze", pole, objetosc))
