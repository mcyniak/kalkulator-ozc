"""Budowa skoroszytu Excel z danymi jednego adresu (szablon pusty lub wypełniony)."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from .konfiguracja import wczytaj_konfiguracje
from .pola import POLA, Pole, Sekcja

FONT = "Arial"

FILL_WEJSCIE = PatternFill("solid", fgColor="FFF2CC")  # żółtawe — do wpisania
FILL_OBLICZ = PatternFill("solid", fgColor="E7E6E6")  # szare — obliczone
FILL_SEKCJA = PatternFill("solid", fgColor="1F4E78")
FILL_NAGLOWEK = PatternFill("solid", fgColor="D9E1F2")
CIENKA = Side(style="thin", color="BFBFBF")
RAMKA = Border(left=CIENKA, right=CIENKA, top=CIENKA, bottom=CIENKA)

# --- budowa skoroszytu ------------------------------------------------------

def nazwij(wb: Workbook, nazwa: str, arkusz: str, zakres: str) -> None:
    wb.defined_names[nazwa] = DefinedName(nazwa, attr_text=f"{quote_sheetname(arkusz)}!{zakres}")


def kol_abs(kol: int, w1: int, w2: int | None = None) -> str:
    c = get_column_letter(kol)
    return f"${c}${w1}" if w2 is None else f"${c}${w1}:${c}${w2}"


def arkusz_biblioteka(wb: Workbook, cfg: dict) -> None:
    ws = wb.create_sheet("Biblioteka")
    ws["A1"] = "BIBLIOTEKA — kopia z pliku konfiguracja.toml. NIE EDYTUJ TUTAJ: zmień plik konfiguracji i wygeneruj szablon ponownie."
    ws["A1"].font = Font(name=FONT, bold=True, color="C00000")
    w = 3

    def naglowek(wiersz: int, teksty: list[str]) -> None:
        for i, t in enumerate(teksty, start=1):
            c = ws.cell(wiersz, i, t)
            c.font = Font(name=FONT, bold=True)
            c.fill = FILL_NAGLOWEK

    def tabela(tytul: str, wiersze: list[dict], kolumny: list[str], nazwy: dict[str, str]) -> None:
        nonlocal w
        ws.cell(w, 1, tytul).font = Font(name=FONT, bold=True, size=11)
        w += 1
        naglowek(w, kolumny)
        start = w + 1
        for r in wiersze:
            w += 1
            for i, k in enumerate(kolumny, start=1):
                ws.cell(w, i, r.get(k, "")).font = Font(name=FONT)
        for kol_nazwa, def_nazwa in nazwy.items():
            nazwij(wb, def_nazwa, "Biblioteka", kol_abs(kolumny.index(kol_nazwa) + 1, start, w))
        w += 2

    tabela("Strefy klimatyczne (PN-EN 12831 NA)", cfg["strefy"], ["nazwa", "theta_e", "theta_me"],
           {"nazwa": "lst_strefy", "theta_e": "bib_theta_e", "theta_me": "bib_theta_me"})
    tabela("Materiały konstrukcyjne", cfg["materialy_konstrukcyjne"], ["nazwa", "lambda", "uwagi"],
           {"nazwa": "lst_mat_konstr", "lambda": "bib_mk_lambda"})
    tabela("Materiały izolacyjne", cfg["materialy_izolacyjne"], ["nazwa", "lambda", "R_stale", "uwagi"],
           {"nazwa": "lst_mat_izol", "lambda": "bib_mi_lambda", "R_stale": "bib_mi_R"})
    tabela("Konstrukcje stropów", cfg["stropy"], ["nazwa", "lambda", "R_stale", "drewniany", "uwagi"],
           {"nazwa": "lst_stropy", "lambda": "bib_st_lambda", "R_stale": "bib_st_R",
            "drewniany": "bib_st_drewn"})

    # U okien i drzwi — tabela 2D: wiersze = progi lat, kolumny = typ
    od = cfg["okna_drzwi_U"]
    typy = ["jednoszybowe", "dwuszybowe", "trzyszybowe", "drzwi"]
    ws.cell(w, 1, "Typowe U okien i drzwi wg roku montażu [W/m²K] — SZACUNEK").font = Font(name=FONT, bold=True, size=11)
    w += 1
    naglowek(w, ["od roku"] + typy)
    nazwij(wb, "bib_U_naglowki", "Biblioteka", f"$B${w}:${get_column_letter(1 + len(typy))}${w}")
    start = w + 1
    for i, rok in enumerate(od["progi_lat"]):
        w += 1
        ws.cell(w, 1, rok).font = Font(name=FONT)
        for j, t in enumerate(typy, start=2):
            ws.cell(w, j, od[t][i]).font = Font(name=FONT)
    nazwij(wb, "bib_progi_lat", "Biblioteka", kol_abs(1, start, w))
    nazwij(wb, "bib_U_tab", "Biblioteka", f"$B${start}:${get_column_letter(1 + len(typy))}${w}")
    w += 2

    # Stałe skalarne
    ws.cell(w, 1, "Stałe (opory przejmowania, parametry)").font = Font(name=FONT, bold=True, size=11)
    w += 1
    naglowek(w, ["nazwa", "wartość"])
    for sekcja in ("opory", "parametry"):
        for k, v in cfg[sekcja].items():
            w += 1
            ws.cell(w, 1, k).font = Font(name=FONT)
            ws.cell(w, 2, v).font = Font(name=FONT)
            nazwij(wb, k, "Biblioteka", f"$B${w}")
    w += 1
    ws.cell(w, 1, "dodatek_U_okna_drzwi").font = Font(name=FONT)
    ws.cell(w, 2, cfg["norma"].get("dodatek_U_okna_drzwi", 0.0)).font = Font(name=FONT)
    nazwij(wb, "dodatek_U_okna_drzwi", "Biblioteka", f"$B${w}")

    for kol, szer in zip("ABCDE", (32, 12, 12, 12, 70)):
        ws.column_dimensions[kol].width = szer


def arkusz_listy(wb: Workbook, cfg: dict) -> None:
    ws = wb.create_sheet("Listy")
    for i, (nazwa, opcje) in enumerate(cfg["listy"].items(), start=1):
        ws.cell(1, i, nazwa).font = Font(name=FONT, bold=True)
        for j, o in enumerate(opcje, start=2):
            ws.cell(j, i, o).font = Font(name=FONT)
        nazwij(wb, f"lst_{nazwa}", "Listy", kol_abs(i, 2, 1 + len(opcje)))
        ws.column_dimensions[get_column_letter(i)].width = 24
    ws.sheet_state = "hidden"


def arkusz_instrukcja(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Instrukcja"
    linie = [
        ("SZABLON DANYCH DO OBLICZENIA OBCIĄŻENIA CIEPLNEGO (OZC) — jeden plik = jeden adres", True),
        ("", False),
        ("Jak wypełniać:", True),
        ("1. Przejdź do arkusza „Dane” i wypełniaj z góry na dół — kolejność jak w protokole audytu.", False),
        ("2. Żółte komórki = do wpisania. Szare = liczone automatycznie (podgląd U i powierzchni).", False),
        ("3. W kolumnie „Źródło” zaznacz, skąd wartość: z protokołu, odczyt niepewny, założenie itd.", False),
        ("4. Wartości z gwiazdką (*) w etykiecie są wstawione domyślnie — zmień, jeśli wiesz lepiej.", False),
        ("5. Pola „U wpisane ręcznie” zostaw puste, chyba że znasz U z dokumentacji.", False),
        ("6. Puste pole = brak danych. Nie wpisuj 0 tam, gdzie po prostu nie wiesz.", False),
        ("", False),
        ("Kolory:", True),
        ("Żółte — dane wejściowe", False),
        ("Szare — obliczone (nie wpisuj)", False),
        ("", False),
        ("Biblioteka materiałów i typowych U jest w arkuszu „Biblioteka” (tylko do podglądu).", False),
    ]
    for i, (t, pogrubienie) in enumerate(linie, start=1):
        ws.cell(i, 1, t).font = Font(name=FONT, bold=pogrubienie, size=12 if i == 1 else 10)
    ws["A12"].fill = FILL_WEJSCIE
    ws["A13"].fill = FILL_OBLICZ
    ws.column_dimensions["A"].width = 110


def arkusz_dane(wb: Workbook, cfg: dict, przyklad: dict | None) -> None:
    ws = wb.create_sheet("Dane", 1)
    naglowki = ["", "Pole", "Wartość", "Jedn.", "Źródło", "Uwagi"]
    for i, t in enumerate(naglowki, start=1):
        c = ws.cell(1, i, t)
        c.font = Font(name=FONT, bold=True)
        c.fill = FILL_NAGLOWEK
        c.border = RAMKA
    ws.freeze_panes = "C2"

    zal = cfg["zalozenia"]
    wartosci = (przyklad or {}).get("wartosci", {})
    zrodla = (przyklad or {}).get("zrodla", {})
    uwagi = (przyklad or {}).get("uwagi", {})

    dv_zrodlo = DataValidation(type="list", formula1="=lst_zrodlo", allow_blank=True)
    ws.add_data_validation(dv_zrodlo)
    dv_listy: dict[str, DataValidation] = {}
    klucze = {p.klucz for p in POLA if isinstance(p, Pole)}
    nieznane = (set(wartosci) | set(zrodla) | set(uwagi)) - klucze
    if nieznane:
        raise ValueError(f"Nieznane pola w przykładzie: {sorted(nieznane)}")

    w = 1
    for p in POLA:
        w += 1
        if isinstance(p, Sekcja):
            c = ws.cell(w, 1, p.tytul)
            c.font = Font(name=FONT, bold=True, color="FFFFFF")
            for k in range(1, 7):
                ws.cell(w, k).fill = FILL_SEKCJA
            continue

        etykieta = p.etykieta + (" *" if p.domyslna_z else "")
        ws.cell(w, 2, etykieta).font = Font(name=FONT)
        ws.cell(w, 4, p.jednostka).font = Font(name=FONT)
        wart = ws.cell(w, 3)
        wart.font = Font(name=FONT)
        wart.border = RAMKA
        wart.alignment = Alignment(horizontal="left")
        nazwij(wb, p.klucz, "Dane", f"$C${w}")

        if p.rodzaj == "calc":
            wart.value = p.formula
            wart.fill = FILL_OBLICZ
            wart.number_format = p.format
            ws.cell(w, 5, "obliczone").font = Font(name=FONT, italic=True, color="808080")
        else:
            wart.fill = FILL_WEJSCIE
            if p.rodzaj in ("num", "int"):
                wart.number_format = p.format
            zr = ws.cell(w, 5)
            zr.font = Font(name=FONT)
            zr.border = RAMKA
            dv_zrodlo.add(zr)

            if wartosci.get(p.klucz) is not None:
                wart.value = wartosci[p.klucz]
            elif p.domyslna_z:
                wart.value = zal[p.domyslna_z]
                zr.value = "założenie domyślne"
            if p.klucz in zrodla:
                zr.value = zrodla[p.klucz]

            if p.rodzaj == "list":
                nazwa_listy = p.lista if p.lista.startswith("lst_") else f"lst_{p.lista}"
                if nazwa_listy not in dv_listy:
                    dv = DataValidation(type="list", formula1=f"={nazwa_listy}", allow_blank=True,
                                        showErrorMessage=True, errorTitle="Wartość spoza listy",
                                        error="Wybierz wartość z listy rozwijanej.")
                    ws.add_data_validation(dv)
                    dv_listy[nazwa_listy] = dv
                dv_listy[nazwa_listy].add(wart)
            elif p.rodzaj in ("num", "int") and p.zakres:
                dv = DataValidation(type="whole" if p.rodzaj == "int" else "decimal",
                                    operator="between", formula1=str(p.zakres[0]),
                                    formula2=str(p.zakres[1]), allow_blank=True,
                                    showErrorMessage=True, errorTitle="Wartość poza zakresem",
                                    error=f"Dopuszczalny zakres: {p.zakres[0]}–{p.zakres[1]} {p.jednostka}")
                ws.add_data_validation(dv)
                dv.add(wart)

        uw = ws.cell(w, 6, uwagi.get(p.klucz, ""))
        uw.font = Font(name=FONT, color="C00000" if p.klucz in uwagi else "000000")
        uw.alignment = Alignment(wrap_text=True, vertical="top")
        if p.podpowiedz:
            wart.comment = Comment(p.podpowiedz, "szablon")

    for kol, szer in zip("ABCDEF", (3, 52, 26, 8, 26, 70)):
        ws.column_dimensions[kol].width = szer




def zbuduj_skoroszyt(dane: dict | None = None) -> Workbook:
    """`dane` = {"wartosci": {...}, "zrodla": {...}, "uwagi": {...}}; None = pusty szablon."""
    cfg = wczytaj_konfiguracje()
    wb = Workbook()
    arkusz_instrukcja(wb)
    arkusz_dane(wb, cfg, dane)
    arkusz_biblioteka(wb, cfg)
    arkusz_listy(wb, cfg)
    wb.active = 1
    return wb
