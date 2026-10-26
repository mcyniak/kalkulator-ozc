"""Dane jednego adresu: wartości pól + źródło + uwagi; odczyt z Excela, normalizacja, założenia."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from .konfiguracja import wczytaj_konfiguracje
from .pola import POLA_WEJSCIOWE, Pole

ZRODLO_DOMYSLNE = "założenie domyślne"


class BladDanych(ValueError):
    """Dane nie pozwalają policzyć wyniku; `problemy` to lista komunikatów dla człowieka."""

    def __init__(self, problemy: list[str]):
        super().__init__("\n".join(problemy))
        self.problemy = problemy


@dataclass
class Miejsce:
    """Miejsce w dokumencie audytu: strona (od 1) i prostokąt [x0, y0, x1, y1] w skali 0–1000 strony."""
    strona: int
    obszar: tuple[int, int, int, int]


@dataclass
class Dane:
    wartosci: dict = field(default_factory=dict)
    zrodla: dict = field(default_factory=dict)
    uwagi: dict = field(default_factory=dict)
    miejsca: dict[str, Miejsce] = field(default_factory=dict)

    def get(self, klucz: str, domyslna=None):
        v = self.wartosci.get(klucz)
        return domyslna if v is None or v == "" else v

    def kopia(self) -> "Dane":
        return Dane(dict(self.wartosci), dict(self.zrodla), dict(self.uwagi), dict(self.miejsca))

    def jako_slownik(self) -> dict:
        return {"wartosci": dict(self.wartosci), "zrodla": dict(self.zrodla), "uwagi": dict(self.uwagi)}


def opcje_listy(pole: Pole) -> list[str]:
    cfg = wczytaj_konfiguracje()
    nazwa = pole.lista or ""
    biblioteki = {
        "lst_strefy": "strefy",
        "lst_mat_konstr": "materialy_konstrukcyjne",
        "lst_mat_izol": "materialy_izolacyjne",
        "lst_stropy": "stropy",
    }
    if nazwa in biblioteki:
        return [r["nazwa"] for r in cfg[biblioteki[nazwa]]]
    return list(cfg["listy"][nazwa.removeprefix("lst_")])


def normalizuj_wartosc(pole: Pole, surowa):
    """Zamienia wartość z Excela/AI/formularza na typ pola. Zwraca None dla pustej.

    Rzuca ValueError z czytelnym komunikatem, gdy wartości nie da się zinterpretować.
    """
    if surowa is None:
        return None
    if isinstance(surowa, str):
        surowa = surowa.strip()
        if surowa in ("", "–", "-"):
            return None
    if pole.rodzaj == "text":
        return str(surowa)
    if pole.rodzaj in ("num", "int"):
        if isinstance(surowa, str):
            try:
                liczba = float(surowa.replace(",", ".").replace(" ", ""))
            except ValueError:
                raise ValueError(f"„{pole.etykieta}”: „{surowa}” nie jest liczbą") from None
        else:
            liczba = float(surowa)
        if pole.zakres and not (pole.zakres[0] <= liczba <= pole.zakres[1]):
            raise ValueError(f"„{pole.etykieta}”: {liczba:g} poza zakresem "
                             f"{pole.zakres[0]:g}–{pole.zakres[1]:g} {pole.jednostka}")
        return int(round(liczba)) if pole.rodzaj == "int" else liczba
    if pole.rodzaj == "list":
        opcje = opcje_listy(pole)
        tekst = str(surowa)
        for o in opcje:
            if o.casefold() == tekst.casefold():
                return o
        raise ValueError(f"„{pole.etykieta}”: „{tekst}” spoza listy ({', '.join(opcje)})")
    raise ValueError(f"Nieobsługiwany rodzaj pola {pole.rodzaj}")


def normalizuj(dane: Dane) -> tuple[Dane, list[str]]:
    """Normalizuje wszystkie wartości; błędne pola zostają puste, a komunikaty wracają w liście."""
    wynik = Dane(zrodla=dict(dane.zrodla), uwagi=dict(dane.uwagi), miejsca=dict(dane.miejsca))
    problemy = []
    for klucz, surowa in dane.wartosci.items():
        pole = POLA_WEJSCIOWE.get(klucz)
        if pole is None:
            continue
        try:
            wynik.wartosci[klucz] = normalizuj_wartosc(pole, surowa)
        except ValueError as e:
            problemy.append(str(e))
            wynik.wartosci[klucz] = None
    return wynik, problemy


def uzupelnij_domyslne(dane: Dane) -> Dane:
    """Wstawia założenia domyślne z konfiguracji do pustych pól i oznacza ich źródło."""
    zal = wczytaj_konfiguracje()["zalozenia"]
    for klucz, pole in POLA_WEJSCIOWE.items():
        if pole.domyslna_z and dane.get(klucz) is None:
            dane.wartosci[klucz] = zal[pole.domyslna_z]
            dane.zrodla[klucz] = ZRODLO_DOMYSLNE
    return dane


def wczytaj_xlsx(sciezka: Path | str) -> Dane:
    """Czyta wypełniony szablon po nazwach zdefiniowanych (kolumna C = wartość, E = źródło, F = uwagi)."""
    wb = load_workbook(sciezka, data_only=False)
    dane = Dane()
    for klucz in POLA_WEJSCIOWE:
        if klucz not in wb.defined_names:
            continue
        for arkusz, adres in wb.defined_names[klucz].destinations:
            ws = wb[arkusz]
            kom = ws[adres.replace("$", "")]
            dane.wartosci[klucz] = kom.value
            zr = ws.cell(kom.row, 5).value
            uw = ws.cell(kom.row, 6).value
            if zr:
                dane.zrodla[klucz] = zr
            if uw:
                dane.uwagi[klucz] = uw
    return dane
