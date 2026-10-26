"""Współczynniki przenikania U przegród — te same wzory co podgląd w szablonie Excel.

Opory przejmowania wg PN-EN ISO 6946; λ materiałów z biblioteki w konfiguracja.toml.
"""
from __future__ import annotations

from .konfiguracja import wczytaj_konfiguracje


def _wiersz(tabela: str, nazwa: str) -> dict:
    for r in wczytaj_konfiguracje()[tabela]:
        if r["nazwa"] == nazwa:
            return r
    raise KeyError(f"Brak „{nazwa}” w bibliotece {tabela}")


def r_izolacji(material: str, grubosc_cm: float | None, miedzy_drewnem: bool = False) -> float:
    """Opór warstwy izolacji [m²K/W]; `miedzy_drewnem` — izolacja między belkami/krokwiami."""
    if material == "Brak":
        return 0.0
    w = _wiersz("materialy_izolacyjne", material)
    if w["R_stale"] > 0:
        return w["R_stale"]
    lam = w["lambda"]
    if miedzy_drewnem:
        p = wczytaj_konfiguracje()["parametry"]
        lam = (1 - p["udzial_drewna"]) * lam + p["udzial_drewna"] * p["lambda_drewna"]
    return (grubosc_cm or 0) / 100 / lam


def r_muru(material: str, grubosc_cm: float) -> float:
    return grubosc_cm / 100 / _wiersz("materialy_konstrukcyjne", material)["lambda"]


def r_stropu(konstrukcja: str, grubosc_cm: float | None) -> float:
    w = _wiersz("stropy", konstrukcja)
    if w["R_stale"] > 0:
        return w["R_stale"]
    return (grubosc_cm or 0) / 100 / w["lambda"]


def stropu_drewniany(konstrukcja: str) -> bool:
    return bool(_wiersz("stropy", konstrukcja)["drewniany"])


def u_sciany(material: str, grubosc_cm: float, izolacja: str, izolacja_cm: float | None) -> float:
    o = wczytaj_konfiguracje()["opory"]
    return 1 / (o["Rsi_poziomy"] + o["Rse"] + o["R_tynki"]
                + r_muru(material, grubosc_cm) + r_izolacji(izolacja, izolacja_cm))


def u_sciany_fundamentowej(material: str, grubosc_cm: float, izolacja: str, izolacja_cm: float | None) -> float:
    o = wczytaj_konfiguracje()["opory"]
    return 1 / (o["Rsi_poziomy"] + o["Rse"] + r_muru(material, grubosc_cm) + r_izolacji(izolacja, izolacja_cm))


def u_podlogi(wylewka_cm: float | None, izolacja: str, izolacja_cm: float | None, chudy_cm: float | None) -> float:
    """U konstrukcji podłogi bez wpływu gruntu (grunt liczony osobno wg PN-EN ISO 13370)."""
    cfg = wczytaj_konfiguracje()
    o, p = cfg["opory"], cfg["parametry"]
    r_beton = ((wylewka_cm or 0) + (chudy_cm or 0)) / 100 / p["lambda_beton"]
    return 1 / (o["Rsi_w_dol"] + o["Rse"] + r_beton + r_izolacji(izolacja, izolacja_cm))


def u_stropu_pod_strychem(konstrukcja: str, grubosc_cm: float | None, izolacja: str, izolacja_cm: float | None) -> float:
    o = wczytaj_konfiguracje()["opory"]
    return 1 / (o["Rsi_w_gore"] + o["Rse_strych"] + r_stropu(konstrukcja, grubosc_cm)
                + r_izolacji(izolacja, izolacja_cm, stropu_drewniany(konstrukcja)))


def u_stropu_nad_piwnica(konstrukcja: str, grubosc_cm: float | None, izolacja: str, izolacja_cm: float | None) -> float:
    o = wczytaj_konfiguracje()["opory"]
    return 1 / (o["Rsi_w_dol"] + o["Rse_piwnica"] + r_stropu(konstrukcja, grubosc_cm)
                + r_izolacji(izolacja, izolacja_cm, stropu_drewniany(konstrukcja)))


def u_dachu(izolacja: str, izolacja_cm: float | None) -> float:
    """Dach skośny z izolacją między krokwiami i wentylowaną szczeliną pod pokryciem."""
    o = wczytaj_konfiguracje()["opory"]
    return 1 / (o["Rsi_w_gore"] + o["Rse_went"] + o["R_wykonczenie_dachu"]
                + r_izolacji(izolacja, izolacja_cm, miedzy_drewnem=True))


def _u_z_tabeli(kolumna: str, rok: int) -> float:
    t = wczytaj_konfiguracje()["okna_drzwi_U"]
    indeks = 0
    for i, prog in enumerate(t["progi_lat"]):
        if rok >= prog:
            indeks = i
    return t[kolumna][indeks]


def u_okien(typ: str, rok: int, material: str | None) -> float:
    dodatek = wczytaj_konfiguracje()["parametry"]["dodatek_alu"] if material == "Aluminium" else 0.0
    return _u_z_tabeli(typ, rok) + dodatek


def u_drzwi(rok: int) -> float:
    return _u_z_tabeli("drzwi", rok)
