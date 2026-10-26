"""Odczyt protokołu audytu (PDF / zdjęcia) przez Claude API → dane do szablonu.

Klucz API: zmienna środowiskowa ANTHROPIC_API_KEY (nigdy w kodzie).
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .dane import Dane, normalizuj, opcje_listy, uzupelnij_domyslne
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
class WynikOdczytu:
    dane: Dane
    pytania: list[str] = field(default_factory=list)
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


SYSTEM = f"""Odczytujesz protokoły audytów budynków mieszkalnych (formularz „Protokół uzgodnień montażowych –
powietrzna pompa ciepła”: zeskanowane strony z odręcznymi wpisami i zaznaczonymi polami wyboru).
Dane posłużą do obliczenia projektowego obciążenia cieplnego budynku (PN-EN 12831) i doboru pompy ciepła.
Błędna wartość podana jako pewna jest gorsza niż brak wartości — człowiek sprawdzi Twój odczyt przed obliczeniem.

Zasady:
1. Wpisuj wyłącznie to, co wynika z dokumentu. Jeśli informacji nie ma, POMIŃ pole — program sam wstawi
   jawnie oznaczone założenie domyślne. Nie zgaduj wartości, których w dokumencie nie ma.
2. Pole `zrodlo`:
   - "protokół" — wartość czytelna i jednoznaczna,
   - "protokół – odczyt niepewny" — pismo mało czytelne albo zapis niejednoznaczny; w `uwaga` opisz,
     co dokładnie widzisz (np. „zapis 20+20 — może dwie warstwy po 20 cm”),
   - "AI – do sprawdzenia" — wartość wywnioskowana pośrednio, np. strefa klimatyczna z lokalizacji,
     „Brak” piwnicy z niezaznaczonego pola.
3. Dla pól typu lista podaj dokładnie jedną z dozwolonych wartości. Liczby z kropką dziesiętną,
   w jednostce pola (grubości w cm, wysokości i wymiary w m).
4. Pole zaznaczone = krzyżyk, ptaszek, kreska lub zakreślenie w kratce. Pusta sekcja (np. brak zaznaczenia
   piwnicy ani piętra) oznacza, że danego elementu nie ma — wtedy „Brak”/0 ze źródłem "AI – do sprawdzenia".
5. Okna: zsumuj liczby sztuk z wszystkich elewacji osobno dla okien małych, średnich i dużych.
6. Strefa klimatyczna: wyznacz z lokalizacji (gmina/powiat) wg mapy stref PN-EN 12831 (I–V),
   źródło "AI – do sprawdzenia", w uwadze podaj, z czego ją wyznaczyłeś.
7. Obrys: z odręcznego szkicu odczytaj wymiary zewnętrzne. Dla prostokąta podaj długość i szerokość.
   Jeśli kształt nie jest prostokątem, wybierz „Inny (podaj pole i obwód)” i — gdy wymiary na to pozwalają —
   policz pole zabudowy i obwód; opisz kształt w uwadze.
8. Mapowanie sekcji formularza:
   - „Strop nad nieogrzewanymi pomieszczeniami” = strop pod nieogrzewanym strychem (pola `strop_*`).
   - „Strop nad ogrzewanymi pomieszczeniami” to strop wewnętrzny — pomiń.
   - „Dach – izolacja … grubość” = `dach_izolacja_grubosc`; materiał tylko gdy podany.
   - „Ściana fundamentowa” = pola `fund_*`; „Podłoga na gruncie” = pola `podloga_*`.
   - „Żądana temperatura w pomieszczeniach” = `temp_zadana` (to życzenie klienta, nie temperatura obliczeniowa).
   - „Dobrane urządzenie … o mocy min. X kW” = `moc_protokol`.
   - „Poddasze użytkowe, śr. wysokość” = `poddasze_uzytkowe` = "Tak" i `h_poddasza`.
   - „Strych ogrzewany/nieogrzewany” lub wypełniona sekcja stropu nad nieogrzewanymi = `strych_nieogrzewany`.
9. Nie przepisuj danych osobowych (imię, nazwisko, telefon, e-mail, podpis). W polu `adres` wpisz adres
   miejsca instalacji (miejscowość, ulica, numer).
10. `pytania`: konkretne pytania do audytora o braki i sprzeczności, które mogą zmienić wynik — np. brak
    wysokości ścianki kolankowej lub okien dachowych przy poddaszu użytkowym, obrys niezgodny z deklarowaną
    powierzchnią, nieczytelne zapisy. Każde pytanie samodzielne, po polsku.
11. `podsumowanie`: 1–2 zdania o budynku i jakości skanu.

Katalog pól (klucz — etykieta [jednostka] (typ) — dozwolone wartości — podpowiedź):
{_katalog_pol()}
"""

SCHEMAT = {
    "type": "object",
    "properties": {
        "pola": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "klucz": {"type": "string", "enum": [k for k in POLA_WEJSCIOWE if k not in POMIJANE]},
                    "wartosc": {"type": "string"},
                    "zrodlo": {"type": "string", "enum": ZRODLA_AI},
                    "uwaga": {"type": "string"},
                },
                "required": ["klucz", "wartosc", "zrodlo", "uwaga"],
                "additionalProperties": False,
            },
        },
        "pytania": {"type": "array", "items": {"type": "string"}},
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
    tresc.append({"type": "text", "text": "Odczytaj ten protokół audytu i wypełnij pola zgodnie z zasadami."})
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
        raise BladOdczytu("Nieprawidłowy klucz API — sprawdź zmienną ANTHROPIC_API_KEY.") from None
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


def przetworz_odpowiedz(surowa: dict) -> WynikOdczytu:
    """Zamienia odpowiedź modelu na Dane; nieprawidłowe wartości trafiają do pytań, nie do obliczeń."""
    dane = Dane()
    for p in surowa.get("pola", []):
        k = p["klucz"]
        if k not in POLA_WEJSCIOWE or k in POMIJANE:
            continue
        dane.wartosci[k] = p["wartosc"]
        dane.zrodla[k] = p["zrodlo"]
        if p.get("uwaga"):
            dane.uwagi[k] = p["uwaga"]
    dane, problemy = normalizuj(dane)
    pytania = list(surowa.get("pytania", [])) + [f"Odczyt AI nie do użycia — {pr}" for pr in problemy]
    return WynikOdczytu(uzupelnij_domyslne(dane), pytania, surowa.get("podsumowanie", ""))


def odczytaj_audyt(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic | None = None) -> WynikOdczytu:
    return przetworz_odpowiedz(zapytaj_claude(pliki, client))
