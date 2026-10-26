"""Raport OZC w Wordzie i PDF — w układzie dotychczasowego raportu FlexiPower Group.

Word generowany przez python-docx (ten sam szablon stylów co w poprzednim narzędziu), wykresy
kołowe czarno-białe z kreskowaniem (matplotlib), PDF przez zainstalowanego na komputerze Worda.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Inches, Pt, RGBColor  # noqa: E402

from .dane import Dane  # noqa: E402
from .konfiguracja import KATALOG_PROJEKTU, wczytaj_konfiguracje  # noqa: E402
from .obliczenia import Wynik  # noqa: E402

LOGO = KATALOG_PROJEKTU / "assets" / "logo_flexipower.png"
FIRMA = "FLEXIPOWER GROUP"
CZCIONKA = "Poppins"  # jak w dotychczasowym raporcie; bez niej Word podstawi podobną
NIEBIESKI = RGBColor(0x1F, 0x73, 0xE6)
SZARY = RGBColor(0x80, 0x80, 0x80)

# Grupy przegród z obliczeń → wiersze raportu (kolejność jak w dotychczasowym raporcie).
WIERSZE_PRZENIKANIA = [
    ("Ściany zewnętrzne", ["Ściany zewnętrzne", "Ściany piwnicy nad terenem"]),
    ("Okna", ["Okna"]),
    ("Drzwi", ["Drzwi"]),
    ("Dach", ["Dach skośny", "Stropodach"]),
    ("Strop/Sufit", ["Strop pod strychem"]),
    ("Podłoga na gruncie", ["Podłoga na gruncie", "Podłoga piwnicy", "Ściany piwnicy w gruncie"]),
    ("Strop nad piwnicą", ["Strop nad piwnicą"]),
    ("Ściany do sąsiada", ["Ściany do sąsiada"]),
]
STALE_WIERSZE = {"Ściany zewnętrzne", "Okna", "Drzwi", "Dach", "Strop/Sufit", "Podłoga na gruncie"}
ETYKIETY_WYKRESU = {"Ściany zewnętrzne": "Ściany", "Podłoga na gruncie": "Podłoga"}
KRESKOWANIA = ["//", "\\\\", "||", "--", "++", "xx", "..", "oo"]
PRZEGRODY_U = [
    ("sciana", "Ściana zewnętrzna"),
    ("fund", "Ściana fundamentowa"),
    ("podloga", "Podłoga na gruncie"),
    ("strop", "Strop nad nieogrzewanym poddaszem"),
    ("dach", "Dach"),
    ("piwn_strop", "Strop nad nieogrzewaną piwnicą"),
    ("okna", "Okna"),
    ("drzwi", "Drzwi"),
]
WENTYLACJA_OPIS = {
    "Grawitacyjna": "Wentylacja naturalna grawitacyjna",
    "Mechaniczna": "Wentylacja mechaniczna",
    "Mechaniczna z odzyskiem": "Wentylacja mechaniczna z odzyskiem ciepła",
}


def liczba(x: float, miejsca: int = 0) -> str:
    return f"{x:.{miejsca}f}".replace(".", ",")


def nazwa_pliku(adres: str, kiedy: datetime) -> str:
    """Np. „OZC_Lipowa 7 00-001 Przykładowo_20260703_145519” — jak w dotychczasowych raportach."""
    czysty = re.sub(r'[<>:"/\\|?*]', "", (adres or "adres").replace(",", " "))
    czysty = re.sub(r"\s+", " ", czysty).strip()
    return f"OZC_{czysty}_{kiedy:%Y%m%d_%H%M%S}"


def wiersze_przenikania(w: Wynik) -> list[tuple[str, float]]:
    rozb = w.rozbicie()
    wiersze = []
    for nazwa, grupy in WIERSZE_PRZENIKANIA:
        phi = sum(rozb.get(g, 0.0) for g in grupy)
        if nazwa in STALE_WIERSZE or phi > 0:
            wiersze.append((nazwa, phi))
    return wiersze


def _wykres_kolowy(tytul: str, dane: list[tuple[str, float]]) -> io.BytesIO:
    dane = [(n, v) for n, v in dane if v > 0]
    fig, ax = plt.subplots(figsize=(6.4, 5.3), dpi=300)
    klinki, _, procenty = ax.pie(
        [v for _, v in dane], labels=[n for n, _ in dane], autopct="%1.1f%%", startangle=90, counterclock=False,
        colors=["white"] * len(dane), wedgeprops={"edgecolor": "black", "linewidth": 2},
        textprops={"fontsize": 15, "fontweight": "bold"}, labeldistance=1.12, pctdistance=0.6)
    for klin, wzor in zip(klinki, KRESKOWANIA):
        klin.set_hatch(wzor)
    for p in procenty:
        p.set_fontsize(14)
        p.set_bbox({"facecolor": "white", "edgecolor": "none", "pad": 1, "alpha": 0.85})
    ax.set_title(tytul, fontsize=17, fontweight="bold", pad=18)
    ax.axis("equal")
    bufor = io.BytesIO()
    fig.savefig(bufor, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    bufor.seek(0)
    return bufor


def _pole_numeru_strony(akapit, kod: str) -> None:
    run = akapit.add_run()
    for typ, tekst in (("begin", None), (None, kod), ("separate", None), ("end", None)):
        if typ:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), typ)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = f" {tekst} "
        run._r.append(el)


def _tabela_klucz_wartosc(doc: Document, wiersze: list[tuple[str, str]], pogrubiona_wartosc: int | None = 0):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(wiersze):
        komorki = t.add_row().cells
        komorki[0].text = k
        komorki[1].text = v
        if i == pogrubiona_wartosc:
            for r in komorki[1].paragraphs[0].runs:
                r.bold = True
    return t


def utworz_docx(dane: Dane, w: Wynik, sciezka: Path, kiedy: datetime) -> Path:
    cfg = wczytaj_konfiguracje()
    n = cfg["norma"]
    geo = w.geometria
    doc = Document()
    normalny = doc.styles["Normal"]
    normalny.font.name = CZCIONKA
    normalny.element.rPr.rFonts.set(qn("w:hAnsi"), CZCIONKA)

    # nagłówek z logo i stopka „Strona X z Y”
    sekcja = doc.sections[0]
    if LOGO.exists():
        sekcja.header.paragraphs[0].add_run().add_picture(str(LOGO), width=Inches(2.5))
    stopka = sekcja.footer.paragraphs[0]
    stopka.alignment = WD_ALIGN_PARAGRAPH.CENTER
    stopka.add_run("Strona ")
    _pole_numeru_strony(stopka, "PAGE")
    stopka.add_run(" z ")
    _pole_numeru_strony(stopka, "NUMPAGES")

    tytul = doc.add_paragraph()
    tytul.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = tytul.add_run("BILANS CIEPLNY BUDYNKU")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(10), NIEBIESKI
    doc.add_paragraph("Norma: PN-EN 12831:2006", style="Intense Quote")

    doc.add_heading("DANE LOKALIZACJI", level=1)
    gmina = (dane.get("gmina") or "").split(" (")[0]
    _tabela_klucz_wartosc(doc, [
        ("Adres:", dane.get("adres") or "—"),
        ("Gmina:", gmina or "—"),
        ("Właściciel:", dane.get("wlasciciel") or "—"),
        ("Data obliczenia:", f"{kiedy:%Y-%m-%d %H:%M}"),
    ])

    doc.add_heading("PARAMETRY BUDYNKU", level=1)
    wentylacja = WENTYLACJA_OPIS.get(w.wentylacja["rodzaj"], w.wentylacja["rodzaj"])
    if w.wentylacja["eta"]:
        wentylacja += f" (η = {w.wentylacja['eta']:.0%})"
    _tabela_klucz_wartosc(doc, [
        ("Powierzchnia ogrzewana:", f"{liczba(geo.pow_ogrzewana)} m²"),
        ("Kubatura:", f"{liczba(geo.kubatura)} m³"),
        ("Strefa klimatyczna:", f"Strefa {dane.get('strefa')} (θe = {liczba(w.theta_e)}°C, "
                                f"θm,e = {liczba(w.theta_me, 1)}°C)"),
        ("Rok budowy:", str(dane.get("rok_budowy") or "—")),
        ("Liczba mieszkańców:", str(dane.get("liczba_osob") or "—")),
        ("Typ wentylacji:", wentylacja),
    ])

    doc.add_heading("SZCZEGÓŁOWE WYNIKI OBLICZEŃ OBCIĄŻENIA CIEPLNEGO (OZC)", level=1)
    wiersze = wiersze_przenikania(w)
    t = doc.add_table(rows=1, cols=2)
    t.style = "Medium Shading 1 Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.rows[0].cells[0].merge(t.rows[0].cells[1]).text = "STRATY PRZEZ PRZENIKANIE"
    for nazwa, phi in wiersze:
        c = t.add_row().cells
        c[0].text, c[1].text = nazwa, f"{phi:.0f} W"
    for nazwa, phi in (("RAZEM PRZENIKANIE (ΦT)", w.phi_T), ("STRATY WENTYLACYJNE (ΦV)", w.phi_V)):
        c = t.add_row().cells
        c[0].text, c[1].text = nazwa, f"{phi:.0f} W"
        for kom in c:
            for r in kom.paragraphs[0].runs:
                r.bold = True

    doc.add_picture(_wykres_kolowy("Rozkład strat ciepła przez przenikanie",
                                   [(ETYKIETY_WYKRESU.get(k, k), v) for k, v in wiersze]), width=Inches(3.5))
    udz_t, udz_v = w.phi_T / w.phi_HL, w.phi_V / w.phi_HL
    doc.add_heading(f"ROZKŁAD STRAT • Przenikanie: {liczba(udz_t * 100, 1)}%; "
                    f"Wentylacja: {liczba(udz_v * 100, 1)}%", level=2)
    doc.add_picture(_wykres_kolowy("Rozkład strat ciepła całkowitych",
                                   [("Przenikanie", w.phi_T), ("Wentylacja", w.phi_V)]), width=Inches(3.5))

    doc.add_heading("PODSTAWOWE WYNIKI OBLICZEŃ BUDYNKU", level=1)
    _tabela_klucz_wartosc(doc, [
        ("Wskaźnik ΦHL odniesiony do kubatury (ΦHL/V):", f"{liczba(w.phi_HL / geo.kubatura, 2)} W/m³"),
        ("Wskaźnik ΦHL odniesiony do powierzchni (ΦHL/A):", f"{liczba(w.phi_HL / geo.pow_ogrzewana, 2)} W/m²"),
        ("Projektowe obciążenie cieplne budynku ΦHL:", f"{w.phi_HL:.0f} W  /  {liczba(w.phi_HL_kW, 2)} kW"),
    ])

    doc.add_heading("WARSTWY BUDOWLANE", level=1)
    obecne = {e.grupa for e in w.elementy}
    potrzebne = {
        "sciana": True, "fund": "Ściany piwnicy nad terenem" in obecne or "Podłoga na gruncie" in obecne,
        "podloga": bool(obecne & {"Podłoga na gruncie", "Podłoga piwnicy"}),
        "strop": bool(obecne & {"Strop pod strychem", "Stropodach"}), "dach": "Dach skośny" in obecne,
        "piwn_strop": "Strop nad piwnicą" in obecne, "okna": "Okna" in obecne, "drzwi": "Drzwi" in obecne,
    }
    t = _tabela_klucz_wartosc(doc, [("Przegroda", "U [W/(m²K)]")] + [
        (opis, liczba(w.U[k], 2)) for k, opis in PRZEGRODY_U if k in w.U and potrzebne[k]], pogrubiona_wartosc=None)
    for kom in t.rows[0].cells:
        for r in kom.paragraphs[0].runs:
            r.bold = True

    doc.add_heading("NORMY I REFERENCJE", level=1)
    for norma in ("PN-EN 12831:2006 - Instalacje ogrzewcze w budynkach - Metoda obliczania projektowego "
                  "obciążenia cieplnego",
                  "PN-EN ISO 6946 - Komponenty budowlane i elementy budynku - Opór cieplny i współczynnik "
                  "przenikania ciepła",
                  "PN-EN ISO 13370 - Cieplne właściwości budynków - Przenoszenie ciepła przez grunt"):
        doc.add_paragraph(f"• {norma}")
    doc.add_paragraph()
    doc.add_paragraph("Korekcje:")
    doc.add_paragraph(f"• Mostki termiczne ΔUtb = +{liczba(n['delta_U_tb'], 2)} W/(m²K) (metoda uproszczona)")
    doc.add_paragraph(f"• Średnia roczna temperatura zewnętrzna θm,e = {liczba(w.theta_me, 1)}°C "
                      f"dla strefy klimatycznej {dane.get('strefa')}")
    doc.add_paragraph(f"• Nadwyżka mocy do nagrzewania ΦRH = {w.phi_RH:.0f} W")

    doc.add_paragraph()
    koniec = doc.add_paragraph()
    koniec.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = koniec.add_run(f"Raport wygenerowany przez: {FIRMA}")
    r.font.size, r.font.color.rgb = Pt(6), SZARY
    r.add_break()
    r2 = koniec.add_run(f"Data: {kiedy:%Y-%m-%d %H:%M:%S}")
    r2.font.size, r2.font.color.rgb = Pt(6), SZARY

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    doc.save(sciezka)
    return sciezka


_SKRYPT_WORD = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
try {
    $w.Visible = $false
    $d = $w.Documents.Open($env:OZC_DOCX, $false, $true)
    $d.SaveAs2($env:OZC_PDF, 17)
    $d.Close($false)
} finally {
    $w.Quit()
}
"""


def docx_na_pdf(docx: Path, pdf: Path) -> bool:
    """Konwersja przez zainstalowanego Worda. Zwraca False, gdy Worda nie ma albo konwersja się nie udała."""
    if os.name != "nt":
        return False
    srodowisko = dict(os.environ, OZC_DOCX=str(docx.resolve()), OZC_PDF=str(pdf.resolve()))
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SKRYPT_WORD],
                       env=srodowisko, check=True, capture_output=True, timeout=180,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.SubprocessError, OSError):
        return False
    return pdf.exists()


def utworz_raport(dane: Dane, w: Wynik, folder: Path, kiedy: datetime | None = None,
                  pdf: bool = True) -> tuple[Path, Path | None]:
    """Tworzy OZC_<adres>_<data>.docx (i .pdf, gdy jest Word) w podanym folderze."""
    kiedy = kiedy or datetime.now()
    rdzen = nazwa_pliku(dane.get("adres") or dane.get("gmina") or "adres", kiedy)
    docx = utworz_docx(dane, w, folder / f"{rdzen}.docx", kiedy)
    plik_pdf = folder / f"{rdzen}.pdf"
    return docx, (plik_pdf if pdf and docx_na_pdf(docx, plik_pdf) else None)
