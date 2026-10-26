"""Orientacyjny dobór mocy pompy i kontrola wyniku przez roczne zużycie paliwa (poza normą)."""
from __future__ import annotations

from .dane import Dane


def kontrola_paliwa(d: Dane, phi_kW: float, cfg: dict) -> dict | None:
    """Szacuje moc projektową z rocznego zużycia paliwa; None, gdy brak danych."""
    k = cfg["kontrola"]
    paliwo, ilosc, jedn = d.get("paliwo_rodzaj"), d.get("paliwo_ilosc"), d.get("paliwo_jednostka")
    dane_paliwa = k["paliwa"].get(paliwo) if paliwo else None
    if not (dane_paliwa and ilosc and jedn) or jedn not in dane_paliwa["energia_kWh"]:
        return None
    q_uzyt = ilosc * dane_paliwa["energia_kWh"][jedn] * dane_paliwa["sprawnosc"]
    q_co = max(0.0, q_uzyt - (d.get("liczba_osob") or 0) * k["cwu_kWh_na_osobe"])
    h_min, h_max = k["godziny_pelnej_mocy"]
    zakres = (q_co / h_max, q_co / h_min)
    wynik = {"q_uzyteczne_kWh": q_uzyt, "q_co_kWh": q_co, "phi_min_kW": zakres[0], "phi_max_kW": zakres[1]}
    if phi_kW < 0.7 * zakres[0] or phi_kW > 1.3 * zakres[1]:
        wynik["ostrzezenie"] = (
            f"Wynik {phi_kW:.1f} kW nie pasuje do zużycia paliwa ({ilosc:g} {jedn} → szacunkowo "
            f"{zakres[0]:.1f}–{zakres[1]:.1f} kW). Sprawdź dane albo zapis zużycia w protokole "
            "(część domu nieogrzewana? dodatkowe źródło ciepła?).")
    return wynik


def dobor_pompy(phi_kW: float, liczba_osob: int | None, blokada_h: float, cfg: dict) -> dict:
    c = cfg["dobor"]
    phi_blok = phi_kW * 24 / (24 - blokada_h) if blokada_h else phi_kW
    cwu = (liczba_osob or 0) * c["cwu_kW_na_osobe"]
    wymagana = phi_blok + cwu
    propozycja = next((m for m in c["typoszereg_kW"] if m >= wymagana), None)
    return {"phi_kW": phi_kW, "blokada_h": blokada_h, "phi_z_blokadami_kW": phi_blok, "cwu_kW": cwu,
            "wymagana_kW": wymagana, "propozycja_kW": propozycja}
