"""Odczyt audytu (PDF / zdjęcia) przez Claude API → dane do obliczeń, z miejscem każdej wartości w dokumencie.

Klucz API: zakładka Ustawienia albo zmienna środowiskowa ANTHROPIC_API_KEY (nigdy w kodzie).
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
import pypdfium2 as pdfium

from .dane import Dane, Miejsce, normalizuj_wartosc, opcje_listy, uzupelnij_domyslne
from .pdf import BLOKADA_PDF
from .podglad import miniatury
from .pola import POLA, POLA_WEJSCIOWE, Sekcja

MODEL = "claude-haiku-5-5"          # domyślny odczyt: ok. 0,01 USD za audyt (krótki namysł)
MODEL_DOKLADNY = "claude-opus-5-5"  # na żądanie, dla trudnych skanów: ok. 0,25 USD za audyt
MODEL_STRON = MODEL                 # wskazanie stron z danymi budynku
MIN_STRON_DO_WYBORU = 3
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
odręcznie wypełniony formularz „Protokół uzgodnień montażowych – powietrzna pompa ciepła” (skan z polami wyboru,
szkicem obrysu i — w nowszych wersjach — tabelą „Typy i wielkości okien” z liczbą okien małych/średnich/dużych
na każdej elewacji), starsze wersje tego formularza (okna opisane na szkicach elewacji) albo komputerowy wydruk
„Ustalenia montażowe pompy ciepła” z tabelami, warstwami przegród i wymiarami ścian elewacyjnych.
Strony ze zdjęciami z wizji, oświadczeniami, protokołem dostosowania obiektu i podpisami pomijaj.
Dane posłużą do obliczenia projektowego obciążenia cieplnego budynku (PN-EN 12831).
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
   i dużych (>2 m²). W tabeli „Typy i wielkości okien” dodaj „Okna małe/średnie/duże … szt.” ze wszystkich
   czterech elewacji (pusta linia = 0 na tej elewacji, gdy na innych elewacjach są wpisy). „Inne (jakie?)” oraz
   drzwi balkonowe/tarasowe przypisz do kategorii wg opisanej wielkości (zwykle duże); gdy wielkości nie da się
   ustalić — pytanie. Gdy podano U okien (np. „Uw = 0,8–0,9”), wpisz `okna_U_reczne` (przy zakresie — górną wartość).
   Gdy elewacje podają tylko powierzchnię okien w m² (np. „Elewacja A, powierzchnia okien: 3,6 m2”), nie zgaduj
   sztuk z rysunków: zsumuj m² ze wszystkich elewacji i wpisz `okna_srednie` = zaokrąglona suma / 1,8,
   źródło "AI – do sprawdzenia", w uwadze podaj sumę m² z każdej elewacji.
   Gdy wszystkie elewacje są puste lub przekreślone — pomiń pola okien i zadaj pytanie.
7. Strefa klimatyczna: wyznacz z lokalizacji (gmina/powiat) wg mapy stref PN-EN 12831 (I–V),
   źródło "AI – do sprawdzenia", w uwadze podaj, z czego ją wyznaczyłeś.
8. Geometria:
   - Szkic obrysu: wymiary zewnętrzne; dla prostokąta długość i szerokość. Prostokąt z niewielkim uskokiem lub
     wcięciem bez podanych wymiarów → „Prostokąt” z wymiarów głównych (źródło "AI – do sprawdzenia") i pytanie
     o uskok. „Inny (podaj pole i obwód)” tylko dla kształtu wyraźnie innego (L, T, U) — wtedy, gdy się da,
     pole zabudowy i obwód; opisz kształt w uwadze.
   - Ściany elewacyjne (szerokość, wysokość, wysokość szczytu): szerokości dwóch prostopadłych ścian to długość
     i szerokość budynku. Liczbę kondygnacji i ich wysokości wyznacz z wysokości ściany do okapu i powierzchni
     ogrzewanej (wysokość w świetle ≈ wysokość ściany na kondygnację − 0,3 m stropu); źródło "AI – do sprawdzenia".
9. Przegrody warstwowe: tynki, okładziny i posadzki pomiń. Najgrubsza warstwa konstrukcyjna ściany →
   `sciana_material`/`sciana_grubosc`, druga warstwa konstrukcyjna (np. cegła przy bloczku) →
   `sciana_material_2`/`sciana_grubosc_2`, izolacja → `sciana_ocieplenie`. „Żelbet” w stropie =
   „Żelbetowy monolityczny”. „Unheated ceiling” / „Strop nad nieogrzewanymi pomieszczeniami” = strop pod
   nieogrzewanym strychem (pola `strop_*`). Podsypki z piasku pod podłogą pomiń (to grunt).
   Gdy strop lub dach ma wypisane warstwy, ale żadnej izolacji, NIE wpisuj „Brak” — pomiń pola izolacji
   i zadaj pytanie (audyty często pomijają ocieplenie). „Brak” tylko przy wyraźnym zaznaczeniu „Izolacja: Nie”.
   Warstwę opisaną „—” o grubości ≥ 5 cm w stropie/podłodze potraktuj jako izolację nieznanego rodzaju
   (`Wełna mineralna` lub `Styropian EPS`), źródło "AI – do sprawdzenia".
10. Mapowanie pól formularza:
   - „Strop nad ogrzewanymi pomieszczeniami” = strop nad najwyższą ogrzewaną kondygnacją. Gdy wyżej jest
     nieogrzewany strych albo nie zaznaczono poddasza użytkowego → pola `strop_*` (strop pod strychem).
     Gdy wyżej jest ogrzewane poddasze użytkowe → to strop wewnętrzny, pomiń.
   - „Strop nad nieogrzewanymi pomieszczeniami” = strop nad nieogrzewaną piwnicą (pola `piwn_strop_*`), gdy
     zaznaczono piwnicę nieogrzewaną. Gdy z dokumentu wynika, że chodzi o strop pod nieogrzewanym strychem
     (np. komputerowe „unheated ceiling”) → pola `strop_*`. Gdy nie da się ustalić — pytanie.
   - „Ilość kondygnacji ogrzewanych”: „Parter, śr. wysokość” = `h_parter`; „Piętro, ilość, śr. wysokość” =
     `liczba_pieter` i `h_pietra`; niezaznaczone piętro = `liczba_pieter` 0; „Piwnica ogrzewana/nieogrzewana”
     = `piwnica` (+ `h_piwnicy`); „Strych ogrzewany/nieogrzewany” → `strych_nieogrzewany`.
   - Szkic obrysu z wymiarami albo „Regularny: długość, szerokość” = `dl_budynku`/`szer_budynku`.
   - „Drzwi garażowe”: wypełnione → `garaz` = "Tak – nieogrzewany" (źródło "AI – do sprawdzenia") i pytanie,
     czy garaż jest w bryle budynku i czy jest ogrzewany; puste albo brak tej sekcji → pomiń (brak garażu).
   - „Dotychczasowy sposób podgrzewania c.o.” → `paliwo_rodzaj` (kocioł na paliwo stałe bez wskazania paliwa =
     „Paliwo stałe (nieokreślone)”, gaz/olej wg zaznaczenia). „Roczne zużycie obecnego paliwa” →
     `paliwo_ilosc` i `paliwo_jednostka`. Gdy brak jednostki, przyjmij typową dla paliwa (gaz → m3/rok,
     węgiel/ekogroszek/pellet → t/rok, olej → l/rok, drewno → mp/rok), źródło "AI – do sprawdzenia",
     i zadaj pytanie o jednostkę.
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


def zapytaj_claude(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic | None = None,
                   dokladny: bool = False) -> dict:
    """Wysyła pliki audytu do Claude i zwraca surowy słownik zgodny ze SCHEMAT.
    dokladny=False: tani model z krótkim namysłem; True: najmocniejszy model (kilkadziesiąt razy droższy)."""
    client = client or anthropic.Anthropic()
    tresc = [_blok_pliku(n, z) for n, z in pliki]
    nazwy = ", ".join(Path(n).stem for n, _ in pliki)
    tresc.append({"type": "text", "text": "Odczytaj ten audyt i wypełnij pola zgodnie z zasadami. "
                  f"Nazwa pliku: „{nazwy}” — zwykle zawiera adres; gdy adres w dokumencie jest nieczytelny, "
                  "porównaj go z nazwą pliku (wtedy źródło \"AI – do sprawdzenia\")."})
    wspolne = {"thinking": {"type": "adaptive"},
               "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
               "messages": [{"role": "user", "content": tresc}]}
    try:
        if dokladny:
            odp = client.beta.messages.create(
                model=MODEL_DOKLADNY, max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMAT}}, **wspolne)
        else:  # tani model zużywa sporo tokenów na namysł — duży limit wymaga strumieniowania
            with client.messages.stream(
                    model=MODEL, max_tokens=32000,
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMAT}},
                    **wspolne) as strumien:
                odp = strumien.get_final_message()
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


# ---------------------------------------------------------------------------
# Wybór stron: do odczytu idą tylko strony z danymi budynku (taniej)
# ---------------------------------------------------------------------------

PYTANIE_STRONY = """To strony audytu budynku mieszkalnego przed montażem pompy ciepła (skan, zdjęcia albo wydruk).
Wskaż numery stron zawierających dane potrzebne do obliczenia obciążenia cieplnego budynku: dane ogólne budynku,
kondygnacje, ściany, stropy, dach, podłoga, okna i drzwi, szkic lub wymiary obrysu i elewacji, źródło ciepła
i zużycie paliwa. Pomiń strony zawierające wyłącznie: oświadczenia, zgody na przetwarzanie danych, podpisy,
protokół konieczności dostosowania obiektu, szkic samej kotłowni, zdjęcia bez danych. W razie wątpliwości stronę
wskaż — pominięcie potrzebnej strony jest gorsze niż wysłanie zbędnej."""

SCHEMAT_STRON = {
    "type": "object",
    "properties": {"strony": {"type": "array", "items": {"type": "integer"}}},
    "required": ["strony"],
    "additionalProperties": False,
}


def _jpeg_b64(obraz) -> str:
    bufor = io.BytesIO()
    obraz.save(bufor, format="JPEG", quality=70)
    return base64.standard_b64encode(bufor.getvalue()).decode("ascii")


def wybierz_strony(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic) -> list[int] | None:
    """Numery stron (od 1, numeracja jak w podglądzie) z danymi budynku; None = czytamy wszystkie strony."""
    try:
        obrazy = miniatury(pliki)
        if len(obrazy) < MIN_STRON_DO_WYBORU:
            return None
        tresc: list[dict] = []
        for nr, obraz in enumerate(obrazy, start=1):
            tresc += [{"type": "text", "text": f"Strona {nr}:"},
                      {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                   "data": _jpeg_b64(obraz)}}]
        tresc.append({"type": "text", "text": PYTANIE_STRONY})
        odp = client.messages.create(
            model=MODEL_STRON, max_tokens=500, thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMAT_STRON}},
            messages=[{"role": "user", "content": tresc}])
        tekst = "".join(b.text for b in odp.content if b.type == "text")
        wybrane = sorted({n for n in json.loads(tekst)["strony"] if 1 <= n <= len(obrazy)})
    except Exception:  # noqa: BLE001 — wybór stron to tylko oszczędność; przy każdym problemie czytamy całość
        return None
    return wybrane if wybrane and len(wybrane) < len(obrazy) else None


def przytnij(pliki: list[tuple[str, bytes]], wybrane: list[int]) -> list[tuple[str, bytes]]:
    """Te same pliki, ale tylko z wybranymi stronami (PDF-y składane od nowa, zdjęcia pomijane w całości)."""
    zostaw, wynik, nr = set(wybrane), [], 0
    for nazwa, zawartosc in pliki:
        if Path(nazwa).suffix.lower() == ".pdf":
            with BLOKADA_PDF:
                zrodlo = pdfium.PdfDocument(zawartosc)
                n = len(zrodlo)
                indeksy = [i for i in range(n) if nr + i + 1 in zostaw]
                if indeksy:
                    nowy = pdfium.PdfDocument.new()
                    nowy.import_pages(zrodlo, indeksy)
                    bufor = io.BytesIO()
                    nowy.save(bufor)
                    wynik.append((nazwa, bufor.getvalue()))
            nr += n
        else:
            nr += 1
            if nr in zostaw:
                wynik.append((nazwa, zawartosc))
    return wynik


def _miejsce(element: dict, mapa_stron: list[int] | None = None) -> Miejsce | None:
    """Miejsce z odpowiedzi modelu; None, gdy model go nie wskazał albo prostokąt jest niepoprawny.
    mapa_stron: oryginalne numery stron wysłanych do modelu (gdy czytał tylko część dokumentu)."""
    strona, obszar = element.get("strona", 0), element.get("obszar") or []
    if strona < 1 or len(obszar) != 4:
        return None
    if mapa_stron:
        if strona > len(mapa_stron):
            return None
        strona = mapa_stron[strona - 1]
    x0, y0, x1, y1 = (max(0, min(1000, int(v))) for v in obszar)
    if x1 <= x0 or y1 <= y0:
        return None
    return Miejsce(strona, (x0, y0, x1, y1))


def przetworz_odpowiedz(surowa: dict, mapa_stron: list[int] | None = None) -> WynikOdczytu:
    """Zamienia odpowiedź modelu na Dane; nieprawidłowe wartości trafiają do pytań, nie do obliczeń."""
    dane = Dane()
    pytania: list[Pytanie] = []
    for p in surowa.get("pola", []):
        k = p["klucz"]
        if k not in POLA_WEJSCIOWE or k in POMIJANE:
            continue
        miejsce = _miejsce(p, mapa_stron)
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
        pytania.append(Pytanie(p["tekst"], [k for k in p.get("klucze", []) if k in POLA_WEJSCIOWE],
                               _miejsce(p, mapa_stron)))
    return WynikOdczytu(uzupelnij_domyslne(dane), pytania, surowa.get("podsumowanie", ""))


def odczytaj_audyt(pliki: list[tuple[str, bytes]], client: anthropic.Anthropic | None = None,
                   dokladny: bool = False) -> WynikOdczytu:
    client = client or anthropic.Anthropic()
    wybrane = wybierz_strony(pliki, client)
    wynik = przetworz_odpowiedz(
        zapytaj_claude(przytnij(pliki, wybrane) if wybrane else pliki, client, dokladny), wybrane)
    if wybrane:
        wynik.podsumowanie = (wynik.podsumowanie + f" Odczytano strony {', '.join(map(str, wybrane))} — "
                              "pozostałe nie zawierały danych budynku.").strip()
    return wynik
