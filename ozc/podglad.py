"""Wycinki skanu audytu: pokazują człowiekowi miejsce, z którego AI odczytało (albo powinno odczytać) wartość."""
from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

from .dane import Miejsce
from .pdf import BLOKADA_PDF

SKALA_RENDERU = 2.0          # ok. 144 dpi — czytelne pismo odręczne
MARGINES = 0.06              # kontekst wokół wskazanego prostokąta (ułamek strony)
MIN_SZER, MIN_WYS = 0.35, 0.10  # najmniejszy wycinek (ułamek strony), żeby było widać etykietę pola


def strony(pliki: list[tuple[str, bytes]]) -> list[Image.Image]:
    """Wszystkie strony audytu jako obrazy, w kolejności, w jakiej widzi je AI (PDF-y stronami, zdjęcia po kolei)."""
    obrazy: list[Image.Image] = []
    for nazwa, zawartosc in pliki:
        if Path(nazwa).suffix.lower() == ".pdf":
            with BLOKADA_PDF:
                pdf = pdfium.PdfDocument(zawartosc)
                obrazy.extend(pdf[i].render(scale=SKALA_RENDERU).to_pil().convert("RGB") for i in range(len(pdf)))
        else:
            obrazy.append(Image.open(io.BytesIO(zawartosc)).convert("RGB"))
    return obrazy


def liczba_stron(pliki: list[tuple[str, bytes]]) -> int:
    with BLOKADA_PDF:
        return sum(len(pdfium.PdfDocument(z)) if Path(n).suffix.lower() == ".pdf" else 1 for n, z in pliki)


def jedna_strona(pliki: list[tuple[str, bytes]], nr: int) -> Image.Image | None:
    """Strona nr (od 1) w numeracji AI — renderowana tylko ta jedna."""
    for nazwa, zawartosc in pliki:
        if Path(nazwa).suffix.lower() == ".pdf":
            with BLOKADA_PDF:
                pdf = pdfium.PdfDocument(zawartosc)
                if nr <= len(pdf):
                    return pdf[nr - 1].render(scale=SKALA_RENDERU).to_pil().convert("RGB")
                nr -= len(pdf)
        else:
            if nr == 1:
                return Image.open(io.BytesIO(zawartosc)).convert("RGB")
            nr -= 1
    return None


def _rozszerz(a: float, b: float, minimum: float) -> tuple[float, float]:
    a, b = a - MARGINES, b + MARGINES
    if b - a < minimum:
        srodek = (a + b) / 2
        a, b = srodek - minimum / 2, srodek + minimum / 2
    przesun = max(0.0, -a) - max(0.0, b - 1.0)
    return max(0.0, a + przesun), min(1.0, b + przesun)


def wycinek(strona: Image.Image, miejsce: Miejsce) -> Image.Image:
    """Fragment strony wokół wskazanego miejsca, z czerwoną ramką na samym wpisie."""
    w, h = strona.size
    x0, y0, x1, y1 = (v / 1000 for v in miejsce.obszar)
    kx0, kx1 = _rozszerz(x0, x1, MIN_SZER)
    ky0, ky1 = _rozszerz(y0, y1, MIN_WYS)
    obraz = strona.copy()
    grubosc = max(2, w // 400)
    ImageDraw.Draw(obraz).rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=(220, 0, 0), width=grubosc)
    return obraz.crop((int(kx0 * w), int(ky0 * h), int(kx1 * w), int(ky1 * h)))


def wycinek_z_plikow(pliki: list[tuple[str, bytes]], miejsce: Miejsce) -> Image.Image | None:
    strona = jedna_strona(pliki, miejsce.strona)
    return wycinek(strona, miejsce) if strona else None
