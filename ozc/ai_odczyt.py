"""Odczyt audytu (PDF / zdjęcia) przez Claude API → dane do obliczeń, z miejscem każdej wartości w dokumencie.

Klucz API: zakładka Ustawienia albo zmienna środowiskowa ANTHROPIC_API_KEY (nigdy w kodzie).
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .dane import Dane, Miejsce, normalizuj_wartosc, opcje_listy, uzupelnij_domyslne
from .pola import POLA, POLA_WEJSCIOWE, Sekcja

MODEL = "claude-opus-5-5"
ZRODLA_AI = ["protokół", "protokół – odczyt niepewny", "AI – do sprawdzenia"]
POMIJANE = {"t_int"}  # wartość normowa, nie z protokołu
TYPY_PLIKOW = {
    ".pdf": ("document", "application/pdf"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".webp": ("image", "image/webp"),
}


class BladOdczytu(RuntimeError):
    pass


@dataclass
class Pytanie:
    tekst: str
    klucze: list[str] = field(default_factory=list)
    miejsce: Miejsce | None = None


@dataclass
class WynikOdczytu:
    dane: Dane
    pytania: list[Pytanie] = field(default_factory=list)
    podsumowanie: str = ""


def _katalog_pol() -> str:
    linie = []
    for p in POLA:
        if isinstance(p, Sekcja):
            linie.append(f"\n## {p.tytul}")
            continue
        if p.rodzaj == "calc" or p.klucz in POMIJANE:
            continue
        typ = {"num": "liczba", "int": "liczba całkowita", "text": "tekst", "list": "lista"}[p.rodzaj]
        opis = f"- `{p.klucz}` — {p.etykieta}" + (f" [{p.jednostka}]" if p.jednostka else "") + f" ({typ})"
        if p.rodzaj == "list":
            opis += " — dozwolone: " + " | ".join(opcje_listy(p))
        if p.podpowiedz:
            opis += f" — {p.podpowiedz}"
        linie.append(opis)
    return "\n".join(linie)


SYSTEM = f"""Odczytujesz audyty budynków mieszkalnych wykonane przed montażem pompy ciepła. Formaty bywają różne:
odręcznie wypełniony formularz „Protokół uzgodnień montażowych” (skan z zaznaczonymi polami wyboru i szkicem)
albo komputerowy wydruk „Ustalenia montażowe pompy ciepła” z tabelami, warstwami przegród i wymiarami ścian
elewacyjnych. Strony ze zdjęciami z wizji, oświadczeniami i podpisami pomijaj.
Dane posłużą do obliczenia projektowego obciążenia cieplnego budynku (PN-EN 12831) i doboru pompy ciepła.
Błędna wartość podana jako pewna jest gorsza niż brak wartości — człowiek sprawdzi Twój odczyt przed obliczeniem.

Zasady:
1. Wpisuj wyłącznie to, co wynika z dokumentu. Jeśli informacji nie ma, POMIŃ pole — program sam wstawi
   jawnie oznaczone założenie domyślne albo poprosi człowieka o wartość. Nie zgaduj.
2. Pole `zrodlo`:
   - "protokół" — wartość czytelna i jednoznaczna,
   - "protokół – odczyt niepewny" — pismo mało czytelne albo zapis niejednoznaczny; w `uwaga` opisz,
     co dokładnie widzisz (np. „zapis 20+20 — może dwie warstwy po 20 cm”),
   - "AI – do sprawdzenia" — wartość wywnioskowana pośrednio (strefa z lokalizacji, wysokości kondygnacji
     z wysokości ściany, „Brak” z niezaznaczonego pola itp.).
3. `strona` i `obszar` — gdzie w dokumencie jest wpis, z którego pochodzi wartość. `strona`: numer strony PDF
   (od 1); przy kilku zdjęciach — numer zdjęcia w kolejności przesłania. `obszar`: [x0, y0, x1, y1] — prostokąt
   w skali 0–1000 względem szerokości i wysokości strony (0,0 = lewy górny róg), obejmujący wpis razem z jego
   etykietą. Wskazuj starannie — człowiek zobaczy wycinek skanu w tym miejscu, gdy będzie sprawdzał wartość.
   Gdy wartość wywnioskowałeś z kilku miejsc, wskaż najważniejsze; gdy nie da się wskazać: 0 i [0, 0, 0, 0].
4. Dla pól typu lista podaj dokładnie jedną z dozwolonych wartości. Liczby z kropką dziesiętną,
   w jednostce pola (grubości w cm, wysokości i wymiary w m).
5. Pole zaznaczone = krzyżyk, ptaszek, kreska lub zakreślenie w kratce. Pusta sekcja piwnicy/piętra oznacza
   brak tego elementu („Brak”/0, źródło "AI – do sprawdzenia"). Okien i drzwi NIE zeruj, gdy dokument ich
   po prostu nie wymienia — pomiń pola i zadaj pytanie.
6. Okna: zsumuj liczby sztuk ze wszystkich elewacji osobno dla okien małych (≤1 m²), średnich (1–2 m²)
   i dużych (>2 m²). Gdy podano U okien (np. „Uw = 0,8–0,9”), wpisz `okna_U_reczne` (przy zakresie — górną wartość).
7. Strefa klimatyczna: wyznacz z lokalizacji (gmina/powiat) wg mapy stref PN-EN 12831 (I–V),
   źródło "AI – do sprawdzenia", w uwadze podaj, z czego ją wyznaczyłeś.
8. Geometria:
   - Szkic obrysu: wymiary zewnętrzne; dla prostokąta długość i szerokość. Kształt inny niż prostokąt —
     „Inny (podaj pole i obwód)” i, gdy się da, pole zabudowy i obwód; opisz kształt w uwadze.
   - Ściany elewacyjne (szerokość, wysokość, wysokość szczytu): szerokości dwóch prostopadłych ścian to długość
     i szerokość budynku. Liczbę kondygnacji i ich wysokości wyznacz z wysokości ściany do okapu i powierzchni
     ogrzewanej (wysokość w świetle ≈ wysokość ściany na kondygnację − 0,3 m stropu); źródło "AI – do sprawdzenia".
9. Przegrody warstwowe: tynki, okładziny i posadzki pomiń. Najgrubsza warstwa konstrukcyjna ściany →
   `sciana_material`/`sciana_grubosc`, druga warstwa konstrukcyjna (np. cegła przy bloczku) →
   `sciana_material_2`/`sciana_grubosc_2`, izolacja → `sciana_ocieplenie`. „Żelbet” w stropie =
   „Żelbetowy monolityczny”. „Unheated ceiling” / „Strop nad nieogrzewanymi pomieszczeniami” = strop pod
   nieogrzewanym strychem (pola `strop_*`). Podsypki z piasku pod podłogą pomiń (to grunt).
10. Mapowanie pól formularza:
   - „Strop nad ogrzewanymi pomieszczeniami” to strop wewnętrzny — pomiń.
   - „Dach – izolacja … grubość” = `dach_izolacja_grubosc`; materiał tylko gdy podany.
   - „Ściana fundamentowa” = pola `fund_*`; „Podłoga na gruncie” = pola `podloga_*`.
   - „Żądana temperatura w pomieszczeniach” = `temp_zadana` (to życzenie klienta, nie temperatura obliczeniowa).
   - „Dobrane urządzenie … o mocy min. X kW” = `moc_protokol`.
   - „Poddasze użytkowe, śr. wysokość” = `poddasze_uzytkowe` = "Tak" i `h_poddasza`.
   - „Stopień szczelności” → `szczelnosc`; „Masywność konstrukcji: duża” → `konstrukcja` = "Ciężka".
11. Dane osobowe: imię i nazwisko właściciela wpisz w `wlasciciel` (trafia do raportu OZC). Telefonu,
    e-maila ani podpisu nie przepisuj. W polu `adres` wpisz adres instalacji w formie
    „Ulica numer, kod pocztowy Miejscowość” (np. „Lipowa 7, 00-001 Przykładowo”).
12. `pytania`: konkretne pytania do audytora o braki i sprzeczności, które mogą zmienić wynik — np. brak okien,
    brak wysokości ścianki kolankowej przy poddaszu użytkowym, obrys niezgodny z deklarowaną powierzchnią,
    nieczytelne zapisy. W `klucze` podaj klucze pól, których pytanie dotyczy, a w `strona`/`obszar` — miejsce
    w dokumencie, gdzie człowiek powinien szukać odpowiedzi (np. tabela okien, szkic). Pytania po polsku.
13. `podsumowanie`: 1–2 zdania o budynku i jakości dokumentu.

Katalog pól (klucz — etykieta [jednostka] (typ) — dozwolone wartości — podpowiedź):
{_katalog_pol()}
"""

_KLUCZE_AI = [k for k in POLA_WEJSCIOWE if k not in POMIJANE]
_MIEJSCE = {
    "strona": {"type": "integer"},
    "obszar": {"type": "array", "items": {"type": "integer"}},
}

SCHEMAT = {
    "type": "object",
    "properties": {
        "pola": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "klucz": {"type": "string", "enum": _KLUCZE_AI},
                    "wartosc": {"type": "string"},
                    "zrodlo": {"type": "string", "enum": ZRODLA_AI},
                    "uwaga": {"type": "string"},
                    **_MIEJSCE,
                },
                "required": ["klucz", "wartosc", "zrodlo", "uwaga", "strona", "obszar"],
                "additionalProperties": False,
            },
        },
        "pytania": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tekst": {"type": "string"},
                    "klucze": {"type": "array", "items": {"type": "string", "enum": _KLUCZE_AI}},
                    **_MIEJSCE,
                },
                "required": ["tekst", "klucze", "strona", "obszar"],
                "additionalProperties": False,
            },
        },
        "podsumowanie": {"type": "string"},
    },
    "required": ["pola", "pytania", "podsumowanie"],
    "additionalProperties": False,
}


def _blok_pliku(nazwa: str, zawartosc: bytes) -> dict:
    rozszerzenie = Path(nazwa).suffix.lower()
    if rozszerzenie not in TYPY_PLIKOW:
        raise BladOdczytu(f"Nieobsługiwany typ pliku: {nazwa} (dozwolone: PDF, JPG, PNG, WEBP)")
    typ, media = TYPY_PLIKOW[rozszerzenie]
    return {"type": typ, "source": {"type": "base64", "media_type": media,
                                    "data": base64.standard_b64encode(zawartosc).decode("ascii")}}


def zapytaj_claude(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic | None = None) -> dict:
    """Wysyła pliki audytu do Claude i zwraca surowy słownik zgodny ze SCHEMAT."""
    client = client or anthropic.Anthropic()
    tresc = [_blok_pliku(n, z) for n, z in pliki]
    tresc.append({"type": "text", "text": "Odczytaj ten audyt i wypełnij pola zgodnie z zasadami."})
    try:
        odp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMAT}},
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": tresc}],
        )
    except anthropic.AuthenticationError:
        raise BladOdczytu("Nieprawidłowy klucz API — wpisz poprawny w zakładce Ustawienia.") from None
    except anthropic.RateLimitError:
        raise BladOdczytu("Przekroczony limit zapytań API — spróbuj za minutę.") from None
    except anthropic.BadRequestError as e:
        raise BladOdczytu(f"API odrzuciło zapytanie: {e.message}") from None
    except anthropic.APIConnectionError:
        raise BladOdczytu("Brak połączenia z API — sprawdź internet.") from None
    except anthropic.APIStatusError as e:
        raise BladOdczytu(f"Błąd API ({e.status_code}) — spróbuj ponownie później.") from None

    if odp.stop_reason == "refusal":
        raise BladOdczytu("Model odmówił odczytu tego dokumentu.")
    if odp.stop_reason == "max_tokens":
        raise BladOdczytu("Odpowiedź modelu została ucięta — spróbuj ponownie.")
    tekst = "".join(b.text for b in odp.content if b.type == "text")
    try:
        return json.loads(tekst)
    except json.JSONDecodeError:
        raise BladOdczytu("Model zwrócił odpowiedź w nieoczekiwanym formacie.") from None


def _miejsce(element: dict) -> Miejsce | None:
    """Miejsce z odpowiedzi modelu; None, gdy model go nie wskazał albo prostokąt jest niepoprawny."""
    strona, obszar = element.get("strona", 0), element.get("obszar") or []
    if strona < 1 or len(obszar) != 4:
        return None
    x0, y0, x1, y1 = (max(0, min(1000, int(v))) for v in obszar)
    if x1 <= x0 or y1 <= y0:
        return None
    return Miejsce(strona, (x0, y0, x1, y1))


def przetworz_odpowiedz(surowa: dict) -> WynikOdczytu:
    """Zamienia odpowiedź modelu na Dane; nieprawidłowe wartości trafiają do pytań, nie do obliczeń."""
    dane = Dane()
    pytania: list[Pytanie] = []
    for p in surowa.get("pola", []):
        k = p["klucz"]
        if k not in POLA_WEJSCIOWE or k in POMIJANE:
            continue
        miejsce = _miejsce(p)
        if miejsce:
            dane.miejsca[k] = miejsce
        try:
            dane.wartosci[k] = normalizuj_wartosc(POLA_WEJSCIOWE[k], p["wartosc"])
        except ValueError as e:
            pytania.append(Pytanie(f"Odczyt AI nie do użycia — {e}", [k], miejsce))
            continue
        dane.zrodla[k] = p["zrodlo"]
        if p.get("uwaga"):
            dane.uwagi[k] = p["uwaga"]
    for p in surowa.get("pytania", []):
        pytania.append(Pytanie(p["tekst"], [k for k in p.get("klucze", []) if k in POLA_WEJSCIOWE], _miejsce(p)))
    return WynikOdczytu(uzupelnij_domyslne(dane), pytania, surowa.get("podsumowanie", ""))


def odczytaj_audyt(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic | None = None) -> WynikOdczytu:
    return przetworz_odpowiedz(zapytaj_claude(pliki, client))
