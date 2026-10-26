"""Raport wyniku (Markdown) i zapis adresu: dane.xlsx + raport.md + wynik.json (+ oryginał audytu)."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from openpyxl.styles import Font

from .dane import Dane
from .obliczenia import Wynik
from .szablon import FONT, zbuduj_skoroszyt


def raport_md(dane: Dane, w: Wynik) -> str:
    rozb = w.rozbicie()
    linie = [
        f"# OZC — {dane.get('adres') or dane.get('gmina') or 'adres bez nazwy'}",
        f"Protokół: {dane.get('nr_protokolu', '—')}, audyt: {dane.get('data_audytu', '—')}, "
        f"obliczono: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"## Projektowe obciążenie cieplne: **{w.phi_HL_kW:.2f} kW**",
        f"Φ_T = {w.phi_T / 1000:.2f} kW (przenikanie), Φ_V = {w.phi_V / 1000:.2f} kW (wentylacja); "
        f"θe = {w.theta_e} °C, θint = {w.theta_int:g} °C, pow. ogrzewana ≈ {w.geometria.pow_ogrzewana:.0f} m²",
        "",
        "| Składowa | kW | udział |",
        "|---|---:|---:|",
    ]
    for nazwa, phi in sorted(rozb.items(), key=lambda kv: -kv[1]):
        linie.append(f"| {nazwa} | {phi / 1000:.2f} | {phi / w.phi_HL:.0%} |")

    if w.dobor:
        b = w.dobor
        linie += ["", "## Dobór pompy (orientacyjnie)",
                  f"- Φ_HL {b['phi_kW']:.2f} kW"
                  + (f" × 24/(24 − {b['blokada_h']:g}) = {b['phi_z_blokadami_kW']:.2f} kW (blokady)" if b["blokada_h"] else ""),
                  f"- + c.w.u. {b['cwu_kW']:.2f} kW = **{b['wymagana_kW']:.2f} kW**",
                  f"- Najbliższa moc z typoszeregu: **{b['propozycja_kW'] or 'poza typoszeregiem'} kW**"
                  + (f" (w protokole: {dane.get('moc_protokol'):g} kW)" if dane.get("moc_protokol") else ""),
                  "- Uwaga: porównuj z mocą pompy przy θe i temperaturze zasilania instalacji, nie z mocą nominalną."]
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
    for tytul, lista in (("Do sprawdzenia", w.ostrzezenia), ("Założenia", w.zalozenia), ("Pytania", list(pytania))):
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
    podsumowanie = {
        "adres": dane.get("adres") or dane.get("gmina"),
        "nr_protokolu": dane.get("nr_protokolu"),
        "data_audytu": dane.get("data_audytu"),
        "obliczono": datetime.now().isoformat(timespec="seconds"),
        "phi_HL_kW": round(w.phi_HL_kW, 2),
        "pow_ogrzewana_m2": round(w.geometria.pow_ogrzewana, 1),
        "rozbicie_kW": {k: round(v / 1000, 3) for k, v in w.rozbicie().items()},
        "propozycja_pompy_kW": (w.dobor or {}).get("propozycja_kW"),
        "moc_w_protokole_kW": dane.get("moc_protokol"),
        "liczba_ostrzezen": len(w.ostrzezenia),
        "ostrzezenia": w.ostrzezenia,
    }
    (folder / "wynik.json").write_text(json.dumps(podsumowanie, ensure_ascii=False, indent=2), encoding="utf-8")
    for nazwa, zawartosc in oryginaly:
        (folder / f"oryginal_{_slug(Path(nazwa).stem)}{Path(nazwa).suffix.lower()}").write_bytes(zawartosc)
    return folder


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
