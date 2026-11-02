"""Zapis adresu: dane.xlsx + raport OZC (Word/PDF) + raport.md + wynik.json (+ oryginał audytu)."""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from openpyxl.styles import Font

from .dane import Dane, normalizuj, wczytaj_xlsx
from .obliczenia import Wynik, oblicz
from .szablon import FONT, zbuduj_skoroszyt
from .ustawienia import folder_raportow


def raport_md(dane: Dane, w: Wynik) -> str:
    rozb = w.rozbicie()
    linie = [
        f"# OZC — {dane.get('adres') or dane.get('gmina') or 'adres bez nazwy'}",
        f"Protokół: {dane.get('nr_protokolu', '—')}, audyt: {dane.get('data_audytu', '—')}, "
        f"obliczono: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"## Projektowe obciążenie cieplne: **{w.phi_HL_kW:.2f} kW**",
        f"Φ_T = {w.phi_T / 1000:.2f} kW (przenikanie), Φ_V = {w.phi_V / 1000:.2f} kW (wentylacja); "
        f"θe = {w.theta_e} °C, θint = {w.theta_int:g} °C, pow. ogrzewana {w.pow_ogrzewana:.0f} m²",
        "",
        "| Składowa | kW | udział |",
        "|---|---:|---:|",
    ]
    for nazwa, phi in sorted(rozb.items(), key=lambda kv: -kv[1]):
        linie.append(f"| {nazwa} | {phi / 1000:.2f} | {phi / w.phi_HL:.0%} |")

    if w.ostrzezenia:
        linie += ["", "## ⚠ Do sprawdzenia", *[f"- {o}" for o in w.ostrzezenia]]
    if w.zalozenia:
        linie += ["", "## Założenia i niepewne odczyty", *[f"- {z}" for z in w.zalozenia]]
    linie += ["", "## Obliczenia krok po kroku", *w.kroki]
    return "\n".join(linie)


def _slug(tekst: str) -> str:
    t = unicodedata.normalize("NFKD", tekst.replace("ł", "l").replace("Ł", "L"))
    t = t.encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:50] or "adres"


def folder_adresu(katalog: Path, dane: Dane) -> Path:
    nazwa = "_".join(filter(None, [str(dane.get("nr_protokolu") or ""), dane.get("adres") or dane.get("gmina") or ""]))
    return katalog / _slug(nazwa or datetime.now().strftime("%Y%m%d_%H%M%S"))


def zapisz_adres(katalog: Path, dane: Dane, w: Wynik, oryginaly: list[tuple[str, bytes]] = (),
                 pytania: list[str] = ()) -> Path:
    folder = folder_adresu(katalog, dane)
    folder.mkdir(parents=True, exist_ok=True)

    wb = zbuduj_skoroszyt(dane.jako_slownik())
    ws = wb.create_sheet("Wyniki", 1)
    ws["A1"] = "Projektowe obciążenie cieplne Φ_HL [kW]"
    ws["B1"] = round(w.phi_HL_kW, 2)
    ws["A1"].font = ws["B1"].font = Font(name=FONT, bold=True, size=12)
    r = 3
    for nazwa, phi in sorted(w.rozbicie().items(), key=lambda kv: -kv[1]):
        ws.cell(r, 1, nazwa).font = Font(name=FONT)
        ws.cell(r, 2, round(phi / 1000, 3)).font = Font(name=FONT)
        r += 1
    r += 1
    ws.cell(r, 1, "Uwaga: wartości wpisane na sztywno w chwili obliczenia — po zmianie danych policz ponownie w aplikacji.").font = Font(name=FONT, italic=True, color="808080")
    pytania = [getattr(p, "tekst", p) for p in pytania]
    for tytul, lista in (("Do sprawdzenia", w.ostrzezenia), ("Założenia", w.zalozenia), ("Pytania", pytania)):
        if lista:
            r += 2
            ws.cell(r, 1, tytul).font = Font(name=FONT, bold=True)
            for t in lista:
                r += 1
                ws.cell(r, 1, t).font = Font(name=FONT)
    ws.column_dimensions["A"].width = 100
    ws.column_dimensions["B"].width = 12
    wb.save(folder / "dane.xlsx")

    (folder / "raport.md").write_text(raport_md(dane, w), encoding="utf-8")
    raporty = _raporty_ozc(dane, w, folder)
    podsumowanie = {
        **raporty,
        "adres": dane.get("adres") or dane.get("gmina"),
        "nr_protokolu": dane.get("nr_protokolu"),
        "data_audytu": dane.get("data_audytu"),
        "obliczono": datetime.now().isoformat(timespec="seconds"),
        "phi_HL_kW": round(w.phi_HL_kW, 2),
        "pow_ogrzewana_m2": round(w.pow_ogrzewana, 1),
        "kubatura_m3": round(w.kubatura, 1),
        "rozbicie_kW": {k: round(v / 1000, 3) for k, v in w.rozbicie().items()},
        "moc_w_protokole_kW": dane.get("moc_protokol"),
        "liczba_ostrzezen": len(w.ostrzezenia),
        "ostrzezenia": w.ostrzezenia,
    }
    (folder / "wynik.json").write_text(json.dumps(podsumowanie, ensure_ascii=False, indent=2), encoding="utf-8")
    for nazwa, zawartosc in oryginaly:
        (folder / f"oryginal_{_slug(Path(nazwa).stem)}{Path(nazwa).suffix.lower()}").write_bytes(zawartosc)
    return folder


def _raporty_ozc(dane: Dane, w: Wynik, folder: Path) -> dict:
    """Raport Word + PDF w folderze adresu (stare wersje usuwane) i kopia w folderze z Ustawień."""
    for stary in list(folder.glob("OZC_*.docx")) + list(folder.glob("OZC_*.pdf")):
        stary.unlink(missing_ok=True)
    from .raport_word import utworz_raport  # matplotlib i python-docx — dopiero przy tworzeniu raportu
    docx, pdf = utworz_raport(dane, w, folder)
    wynik = {"raport_docx": str(docx), "raport_pdf": str(pdf) if pdf else None, "kopia_raportu": None}
    cel = folder_raportow()
    if cel:
        try:
            cel.mkdir(parents=True, exist_ok=True)
            for plik in filter(None, (docx, pdf)):
                shutil.copy2(plik, cel / plik.name)
            wynik["kopia_raportu"] = str(cel)
        except OSError as e:
            wynik["kopia_raportu_blad"] = f"Nie udało się skopiować raportu do {cel}: {e}"
    return wynik


def raport_dla_folderu(folder: Path) -> dict:
    """Tworzy raport dla adresu zapisanego wcześniej (z jego dane.xlsx) i aktualizuje wynik.json."""
    dane, _ = normalizuj(wczytaj_xlsx(folder / "dane.xlsx"))
    raporty = _raporty_ozc(dane, oblicz(dane), folder)
    plik = folder / "wynik.json"
    podsumowanie = json.loads(plik.read_text(encoding="utf-8")) if plik.exists() else {}
    podsumowanie.update(raporty)
    plik.write_text(json.dumps(podsumowanie, ensure_ascii=False, indent=2), encoding="utf-8")
    return podsumowanie


def lista_adresow(katalog: Path) -> list[dict]:
    wyniki = []
    for plik in sorted(katalog.glob("*/wynik.json")):
        try:
            dane = json.loads(plik.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dane["folder"] = str(plik.parent)
        wyniki.append(dane)
    return sorted(wyniki, key=lambda x: x.get("obliczono", ""), reverse=True)
