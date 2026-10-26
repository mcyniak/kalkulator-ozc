"""Import komputerowych audytów FlexiPower („Ustalenia montażowe pompy ciepła”) z warstwy tekstowej PDF — bez AI.

Wartości odczytane wprost mają źródło „protokół”; wyliczone (np. liczba kondygnacji z wysokości ścian,
U z warstw, wymiary rzutu ze ścian elewacyjnych) — „wyliczone z audytu”, do potwierdzenia przez człowieka.
"""
from __future__ import annotations

import math
import re
import statistics as st

import pypdfium2 as pdfium

from .ai_odczyt import Pytanie, WynikOdczytu
from .dane import Dane, Miejsce, uzupelnij_domyslne
from .konfiguracja import wczytaj_konfiguracje
from .pdf import BLOKADA_PDF

ZRODLO_WPROST = "protokół"
ZRODLO_WYLICZONE = "wyliczone z audytu"      # szacunek — do potwierdzenia przez człowieka
ZRODLO_PRZELICZONE = "przeliczone z audytu"  # jednoznacznie przeliczone (np. U z warstw) — bez potwierdzania
IZOLACJE = {"Styropian", "Wełna mineralna", "Wełna skalna", "Pianka PUR", "Pianka PIR"}
POMIJANE = {"Podsypka z piasku", "Inne"}
NIEZNANA = "—"
WYS_KONDYGNACJI = 2.8  # [m] na kondygnację z biegiem stropu — do wyliczania liczby kondygnacji z wysokości ścian


# ---------------------------------------------------------------------------
# Tekst PDF i lokalizacja napisów
# ---------------------------------------------------------------------------

def rozpoznaj(zawartosc: bytes) -> bool:
    """Czy PDF to komputerowy audyt FlexiPower z danymi budynku (warstwa tekstowa)."""
    try:
        with BLOKADA_PDF:
            pdf = pdfium.PdfDocument(zawartosc)
            t = pdf[0].get_textpage().get_text_range()
    except Exception:  # noqa: BLE001 — uszkodzony/nie-PDF: niech zajmie się nim AI
        return False
    return "Ustalenia montażowe pompy ciepła" in t and "Warstwy budynku" in t


class _Strony:
    """Strony PDF z warstwą tekstu wczytane raz — do odczytu tekstu i wyszukiwania miejsc (pod blokadą PDFium)."""

    def __init__(self, zawartosc: bytes):
        with BLOKADA_PDF:
            self.pdf = pdfium.PdfDocument(zawartosc)
            self.strony = [(self.pdf[i], self.pdf[i].get_textpage()) for i in range(len(self.pdf))]
            self.tekst = oczysc("\n".join(tp.get_text_range() for _, tp in self.strony))

    def znajdz(self, fraza: str) -> Miejsce | None:
        """Miejsce pierwszego wystąpienia frazy — prostokąt w skali 0–1000, na całą szerokość tabeli."""
        with BLOKADA_PDF:
            for nr, (strona, tp) in enumerate(self.strony):
                traf = tp.search(fraza, match_case=False).get_next()
                if not traf:
                    continue
                indeks, ile = traf
                ramki = [tp.get_charbox(i) for i in range(indeks, indeks + ile)]
                _, h = strona.get_size()
                y0 = max(0, int((h - max(r[3] for r in ramki)) / h * 1000) - 5)
                y1 = min(1000, int((h - min(r[1] for r in ramki)) / h * 1000) + 25)
                return Miejsce(nr + 1, (120, y0, 880, y1))
        return None


def oczysc(t: str) -> str:
    """Usuwa nagłówki stron i skleja wiersze złamane przez łamanie tekstu w PDF."""
    t = t.replace("\r", "")
    t = re.sub(r"\n(?:FLEXIPOWER GROUP|DOKUMENTACJA POWYKONAWCZA)(?=\n)", "", t)
    t = re.sub(r"grubość (\d+(?:[.,]\d+)?) ?\n?cm", r"grubość \1 cm", t)
    return re.sub(r",\s*\n(izolacja)", r", \1", t)


# ---------------------------------------------------------------------------
# Parsowanie tekstu
# ---------------------------------------------------------------------------

def _liczba(t: str | None) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", t or "")
    return float(m.group().replace(",", ".")) if m else None


def _zakres_u(t: str) -> tuple[float, float] | None:
    """„Uw = 0,9–1,1” → (0,9; 1,1); „Ud ≤ 1,3 (2010 r.)” → (1,3; 1,3). Pomija lata, jednostki i dopiski w nawiasach."""
    t = re.sub(r"\(.*?\)", " ", t or "")
    t = re.split(r"\s*W\s*/", t)[0]  # ucina „W/m2K” i wszystko dalej
    liczby = [v for v in (float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", t)) if 0.3 <= v <= 7.0]
    return (min(liczby), max(liczby)) if liczby else None


def _warstwy(blok: str) -> list[tuple[str, float]]:
    return [(m.group(1).strip(), float(m.group(2).replace(",", ".")))
            for m in re.finditer(r"Warstwa \d+: (.+?) — grubość (\d+(?:[.,]\d+)?) cm", blok)]


def parsuj_tekst(t: str) -> dict:
    """Surowe dane audytu z tekstu PDF (bez interpretacji)."""
    def pole(etykieta):
        m = re.search(rf"^{re.escape(etykieta)}:? (.+)$", t, flags=re.M)
        return m.group(1).strip() if m else None

    r = {k: pole(e) for k, e in (
        ("adres", "Adres"), ("gmina", "Gmina"), ("wlasciciel", "Właściciel"), ("masywnosc", "Masywność konstrukcji"),
        ("szczelnosc", "Stopień szczelności obudowy"), ("wentylacja", "Typ wentylacji"))}
    for k, e in (("osoby", "Liczba mieszkańców"), ("pow", "Powierzchnia ogrzewana"), ("rok", "Rok budowy"),
                 ("kondygnacje", "Liczba kondygnacji ogrzewanych")):
        r[k] = _liczba(pole(e))

    przegrody = {}
    m = re.search(r"Warstwy budynku (.*?)(?:\nWarstwy ścian|\nŚciany elewacyjne)", t, flags=re.S)
    if m:
        for nazwa, blok in re.findall(r"(?:^|\n)\s*([^\n:]+?):\n(.*?)(?=\n[^\n:]+?:\n|\Z)", m.group(1), flags=re.S):
            przegrody[nazwa.strip()] = _warstwy(blok)
    r["przegrody"] = przegrody

    elewacje = []
    m = re.search(r"Ściany elewacyjne (.*?)(?:\nProtokół uzgodnień|\Z)", t, flags=re.S)
    if m:
        for blok in re.split(r"Ściana elewacyjna nr \d+:", m.group(1))[1:]:
            e = {"ksztalt": (re.search(r"Kształt: (\S+)", blok) or [None, None])[1]}
            for klucz, wzor in (("szer", r"szerokość: ([\d.,]+)"), ("wys", r"wysokość: ([\d.,]+)"),
                                ("podstawa", r"szer\. podstawy: ([\d.,]+)"), ("szczyt", r"wys\. szczytu: ([\d.,]+)"),
                                ("bok", r"wysokość boku: ([\d.,]+)")):
                mm = re.search(wzor, blok)
                e[klucz] = float(mm.group(1).replace(",", ".")) if mm else None
            e["okna"] = [{"pow": float(a.replace(",", ".")), "U": _zakres_u(u)}
                         for a, u in re.findall(r"Okno \d+: powierzchnia: ([\d.,]+), izolacja: ([^\n]*)", blok)]
            # okna opisane bez powierzchni — znamy tylko U
            e["okna_bez_pow"] = [_zakres_u(u) for u in re.findall(r"Okno \d+: izolacja: ([^\n]*)", blok)]
            e["drzwi"] = [{"typ": typ, "pow": float(a.replace(",", ".")), "U": _zakres_u(u)}
                          for typ, a, u in re.findall(r"Drzwi \d+: typ: (\S+), powierzchnia: ([\d.,]+), izolacja: ([^\n]*)", blok)]
            elewacje.append(e)
    r["elewacje"] = elewacje
    return r


# ---------------------------------------------------------------------------
# Interpretacja → Dane
# ---------------------------------------------------------------------------

def _u_z_warstw(warstwy, rsi, rse, lam, nieznana_jako_izolacja) -> tuple[float | None, list[str], list[str]]:
    """(U, nieznane warstwy — pominięte, warstwy przyjęte jako izolacja). „—” ≥ 5 cm w stropie/podłodze = izolacja."""
    if not warstwy:
        return None, [], []
    r, nieznane, zalozone = rsi + rse, [], []
    for m, g in warstwy:
        if m in POMIJANE:
            continue
        if m in lam:
            r += g / 100 / lam[m]
        elif m == NIEZNANA and nieznana_jako_izolacja and g >= 5:
            r += g / 100 / 0.040
            zalozone.append(f"„—” {g:g} cm")
        else:
            nieznane.append(f"{m} {g:g} cm")
    return 1 / r, nieznane, zalozone


def _ma_izolacje(warstwy) -> bool:
    return any(m in IZOLACJE or (m == NIEZNANA and g >= 5) for m, g in warstwy)


def _opis(warstwy) -> str:
    return " + ".join(f"{m} {g:g} cm" for m, g in warstwy)


def _okna_w_kategorie(powierzchnie: list[float]) -> dict:
    """Okna z audytu (powierzchnie) → liczby i średnie powierzchnie w kategoriach szablonu (małe/średnie/duże)."""
    kat = {"male": [], "srednie": [], "duze": []}
    for a in powierzchnie:
        if a <= 1.0:
            kat["male"].append(a)
        elif a <= 2.0:
            kat["srednie"].append(a)
        else:
            n = math.ceil(a / 6.0)  # duże przeszklenia dzielimy na „okna” po ≤ 6 m² (zakres pola 1,5–8 m²)
            kat["duze"] += [a / n] * n
    wynik = {}
    for k, lista in kat.items():
        wynik[f"okna_{k}"] = len(lista)
        if lista:
            wynik[f"pow_okna_{k}"] = round(sum(lista) / len(lista), 2)
    return wynik


def _wymiary_rzutu(el: list[dict]) -> tuple[float, float | None, bool]:
    """(długość, szerokość, czy szerokość pewna). Szerokość = podstawa ściany szczytowej albo druga największa
    szerokość ≥ 40% długości — krótkie odcinki (ganek, wykusz, garaż) nie są brane za bok budynku."""
    szer = [e["szer"] or e["podstawa"] for e in el if (e["szer"] or e["podstawa"])]
    dl = max(szer)
    szczyty = [e["podstawa"] for e in el if e["ksztalt"] == "prostokąt_trójkąt" and e["podstawa"]]
    if szczyty and max(szczyty) < dl:
        return dl, max(szczyty), True
    kandydaci = sorted({s for s in szer if 0.4 * dl <= s < dl}, reverse=True)
    if kandydaci:
        return dl, kandydaci[0], len(set(szer)) <= 2
    return dl, None, False


def interpretuj(r: dict, strony: _Strony | None = None) -> WynikOdczytu:
    cfg = wczytaj_konfiguracje()
    lam = cfg["warstwy_audytu"]
    d = Dane()
    pytania: list[Pytanie] = []
    szacowane: set[str] = set()  # pola wyliczone z założeniem — zostają „do potwierdzenia”

    def znajdz(fraza):
        return strony.znajdz(fraza) if strony is not None and fraza else None

    def ustaw(klucz, wartosc, zrodlo=ZRODLO_WPROST, uwaga=None, szukaj=None):
        if wartosc is None:
            return
        d.wartosci[klucz] = wartosc
        d.zrodla[klucz] = zrodlo
        if uwaga:
            d.uwagi[klucz] = uwaga
        miejsce = znajdz(szukaj)
        if miejsce:
            d.miejsca[klucz] = miejsce

    def pytaj(tekst, klucze, szukaj=None):
        pytania.append(Pytanie(tekst, klucze, znajdz(szukaj)))

    def u_przegrody(klucz, warstwy, rsi, rse, nieznana_jako_izolacja, opis_przegrody, szukaj, uwaga_prefiks="U z warstw"):
        """Ustawia U z warstw; nieznane lub założone warstwy → pytanie i pole do potwierdzenia."""
        u, nieznane, zalozone = _u_z_warstw(warstwy, rsi, rse, lam, nieznana_jako_izolacja)
        if not u:
            return None
        ustaw(klucz, round(u, 3), ZRODLO_WYLICZONE, f"{uwaga_prefiks}: {_opis(warstwy)}", szukaj=szukaj)
        if nieznane or zalozone:
            szacowane.add(klucz)
            czesci = ([f"pominięto nieznane warstwy: {', '.join(nieznane)}"] if nieznane else []) + \
                     ([f"warstwę {', '.join(zalozone)} przyjęto jako izolację (λ 0,040)"] if zalozone else [])
            pytaj(f"{opis_przegrody}: {'; '.join(czesci)} — sprawdź.", [klucz], szukaj)
        return u

    # --- podstawowe ---
    ustaw("adres", r["adres"], szukaj="Adres:")
    ustaw("gmina", r["gmina"], szukaj="Gmina:")
    ustaw("wlasciciel", r["wlasciciel"], szukaj="Właściciel:")
    ustaw("liczba_osob", int(r["osoby"]) if r["osoby"] else None, szukaj="Liczba mieszkańców")
    ustaw("pow_ogrz_dekl", r["pow"], szukaj="Powierzchnia ogrzewana")
    ustaw("rok_budowy", int(r["rok"]) if r["rok"] else None, szukaj="Rok budowy")
    szcz = (r["szczelnosc"] or "").split(" ")[0]
    ustaw("szczelnosc", szcz if szcz in ("Niski", "Średni", "Wysoki") else None, szukaj="Stopień szczelności")
    mas = (r["masywnosc"] or "").split(" ")[0]
    ustaw("konstrukcja", {"Duża": "Ciężka", "Średnia": "Średnia", "Mała": "Lekka"}.get(mas), szukaj="Masywność")
    went = (r["wentylacja"] or "").lower()
    if "grawitac" in went or "naturaln" in went:
        ustaw("wentylacja", "Grawitacyjna", szukaj="Typ wentylacji")
    elif "mechaniczn" in went:
        ustaw("wentylacja", "Mechaniczna", ZRODLO_WYLICZONE, "Audyt nie podaje odzysku ciepła — jeśli jest, zmień "
              "na „z odzyskiem” i wpisz sprawność.", szukaj="Typ wentylacji")
        szacowane.add("wentylacja")

    p = r["przegrody"]

    # --- przegrody pionowe i podłoga ---
    sciana = p.get("Ściana zewnętrzna", [])
    if u_przegrody("sciana_U_reczne", sciana, 0.13, 0.04, False, "Ściana zewnętrzna", "Ściana zewnętrzna:"):
        grub = sum(g for m, g in sciana if m not in POMIJANE)
        ustaw("sciana_grubosc", max(5.0, grub - 3), ZRODLO_WYLICZONE)
        ustaw("sciana_ocieplenie_grubosc", 0.0, ZRODLO_WYLICZONE)
    u_przegrody("fund_U_reczne", p.get("Ściana fundamentowa", []), 0.13, 0.04, False, "Ściana fundamentowa",
                "Ściana fundamentowa:")
    ustaw("piwnica", "Brak", ZRODLO_WYLICZONE, "Audyt podaje podłogę na gruncie — przyjęto brak piwnicy.")
    u_przegrody("podloga_U_reczne", p.get("Podłoga na gruncie", []), 0.17, 0.04, True, "Podłoga na gruncie",
                "Podłoga na gruncie:", "U z warstw (bez gruntu)")

    # --- kondygnacje i poddasze ---
    sufit_ogrz = "Strop / sufit ogrzewany" in p
    kond_audyt = int(r["kondygnacje"]) if r.get("kondygnacje") else None
    # „Strop / sufit ogrzewany” = jedyna górna przegroda. Przy 1 kondygnacji to sufit parteru, nie poddasze.
    poddasze = sufit_ogrz and kond_audyt != 1

    # --- strop pod nieogrzewanym strychem / dach nad poddaszem ogrzewanym ---
    for nazwa, pole, rsi_rse in (("unheated ceiling", "strop", (0.10, 0.10)),
                                 ("Strop / sufit ogrzewany", "dach" if poddasze else "strop", (0.10, 0.04))):
        if nazwa not in p:
            continue
        warstwy = p[nazwa]
        if _ma_izolacje(warstwy):
            u_przegrody(f"{pole}_U_reczne", warstwy, *rsi_rse, True, nazwa, nazwa)
            if pole == "dach" and "unheated ceiling" not in p:
                # jedyna górna przegroda — także sufit poddasza pod strychem (jętki)
                u_przegrody("strop_U_reczne", warstwy, 0.10, 0.10, True, nazwa, nazwa, "Sufit poddasza = dach")
        else:  # brak izolacji: program przyjmie jawne założenie i poprosi o potwierdzenie
            cel = "strop" if pole == "strop" or "unheated ceiling" not in p else pole
            if cel == "strop":
                konstr = "Drewniany" if any(m == "Drewno" for m, _ in warstwy) else "Żelbetowy monolityczny"
                ustaw("strop_konstrukcja", konstr, ZRODLO_WYLICZONE, f"Warstwy w audycie: {_opis(warstwy) or 'brak'}",
                      szukaj=nazwa)
                ustaw("strop_grubosc", next((g for m, g in warstwy if m.startswith(("Żelbet", "Drewno", "Beton"))), 10.0),
                      ZRODLO_WYLICZONE)
            po_polsku = {"unheated ceiling": "stropu pod nieogrzewanym strychem",
                         "Strop / sufit ogrzewany": "dachu / sufitu nad częścią ogrzewaną"}[nazwa]
            pytaj(f"Audyt nie podaje izolacji {po_polsku} (warstwy: {_opis(warstwy) or 'brak'}) — "
                  "sprawdź, czy jest ocieplenie.", [f"{cel}_izolacja_grubosc"], nazwa)

    # --- geometria ze ścian elewacyjnych ---
    el = r["elewacje"]
    wys = [e["wys"] or e["bok"] for e in el if (e["wys"] or e["bok"])]
    if any(e["szer"] or e["podstawa"] for e in el) and wys:
        h_e = st.median(wys)
        dl, sz, sz_pewna = _wymiary_rzutu(el)
        if kond_audyt:
            kond = kond_audyt
        elif poddasze:
            kond = max(1, int(h_e // WYS_KONDYGNACJI)) + 1
        else:
            kond = max(1, round(h_e / WYS_KONDYGNACJI))
        pelne = max(1, kond - 1) if poddasze else kond
        grub_sc = (d.get("sciana_grubosc", 40) + 3) / 100
        if sz is None and r["pow"]:
            sz = max(4.0, r["pow"] / kond / max(dl - 2 * grub_sc, 1) + 2 * grub_sc)
            sz_pewna = False
            pytaj(f"Audyt podaje jedną szerokość ściany ({dl:g} m) — drugi wymiar ({sz:.1f} m) wyliczono z powierzchni "
                  "ogrzewanej. Sprawdź.", ["szer_budynku"], "Ściana elewacyjna nr")
        if not sz_pewna:
            szacowane.add("szer_budynku")
        opis_elew = "; ".join(f"{e['ksztalt']} {e['szer'] or e['podstawa']}×{e['wys'] or e['bok']}"
                              + (f" (szczyt {e['szczyt']})" if e.get("szczyt") else "") for e in el)
        ustaw("obrys", "Prostokąt", ZRODLO_WYLICZONE)
        ustaw("dl_budynku", dl, ZRODLO_WYLICZONE, f"Ze ścian elewacyjnych: {opis_elew}", szukaj="Ściana elewacyjna nr")
        ustaw("szer_budynku", round(sz, 2) if sz else None, ZRODLO_WYLICZONE, f"Ze ścian elewacyjnych: {opis_elew}",
              szukaj="Ściana elewacyjna nr")
        zr_kond = ZRODLO_WPROST if kond_audyt else ZRODLO_WYLICZONE
        gdzie_kond = "Liczba kondygnacji" if kond_audyt else "Ściana elewacyjna nr"  # wycinek: skąd wartość
        if not kond_audyt:
            szacowane |= {"liczba_pieter", "h_parter", "h_kolanka"}
        uw_kond = None if kond_audyt else f"Wyliczono z wysokości ścian ({h_e:g} m) — sprawdź."
        szczyty = [e for e in el if e["ksztalt"] == "prostokąt_trójkąt" and e["szczyt"] and e["bok"] and e["podstawa"]]
        if szczyty:
            s0 = szczyty[0]
            kat = math.degrees(math.atan((s0["szczyt"] - s0["bok"]) / (s0["podstawa"] / 2)))
            ustaw("dach_rodzaj", "Skośny dwuspadowy", ZRODLO_WYLICZONE)
            ustaw("kat_dachu", round(min(max(kat, 10), 60)), ZRODLO_WYLICZONE,
                  f"Ze ściany szczytowej: podstawa {s0['podstawa']:g} m, szczyt {s0['szczyt']:g} m, bok {s0['bok']:g} m")
        elif poddasze:
            ustaw("dach_rodzaj", "Skośny dwuspadowy", ZRODLO_WYLICZONE)
            ustaw("kat_dachu", 35, ZRODLO_WYLICZONE, "Audyt nie podaje wymiarów ściany szczytowej — przyjęto 35°.")
            szacowane.add("kat_dachu")
            pytaj("Audyt nie podaje kąta dachu (brak wymiarów szczytu) — przyjęto 35°, sprawdź.", ["kat_dachu"],
                  "Ściana elewacyjna nr")
        if poddasze:
            szacowane.add("poddasze_uzytkowe")
            ustaw("poddasze_uzytkowe", "Tak", ZRODLO_WYLICZONE, "Audyt podaje „strop / sufit ogrzewany” — przyjęto "
                  "ogrzewane poddasze pod skosami.", szukaj="Strop / sufit ogrzewany")
            ustaw("strych_nieogrzewany", "Tak", ZRODLO_WYLICZONE)
            ustaw("liczba_pieter", max(0, pelne - 1), zr_kond, uw_kond, szukaj=gdzie_kond)
            ustaw("h_parter", 2.5, ZRODLO_WYLICZONE)
            ustaw("h_pietra", 2.5, ZRODLO_WYLICZONE)
            ustaw("h_poddasza", 2.5, ZRODLO_WYLICZONE)
            ustaw("h_kolanka", round(max(0.0, min(h_e - pelne * WYS_KONDYGNACJI, 2.0)), 2), ZRODLO_WYLICZONE,
                  f"Wysokość ścian {h_e:g} m − {pelne} kondygnacje × {WYS_KONDYGNACJI} m")
        else:
            h = round(max(2.2, min(h_e / kond - 0.3, 3.5)), 2)
            ustaw("poddasze_uzytkowe", "Nie", ZRODLO_WYLICZONE)
            ustaw("strych_nieogrzewany", "Tak", ZRODLO_WYLICZONE)
            ustaw("liczba_pieter", kond - 1, zr_kond, uw_kond, szukaj=gdzie_kond)
            ustaw("h_parter", h, ZRODLO_WYLICZONE, f"Wysokość ścian {h_e:g} m / {kond} kondygnacje − strop",
                  szukaj="Ściana elewacyjna nr")
            ustaw("h_pietra", h, ZRODLO_WYLICZONE)

    # --- okna i drzwi ---
    okna = [o for e in el for o in e["okna"]]
    u_bez_pow = [u for e in el for u in e.get("okna_bez_pow", [])]
    drzwi = [x for e in el for x in e["drzwi"]]
    balkonowe = [x for x in drzwi if x["typ"] == "balkonowe_tarasowe"]
    bramy = [x for x in drzwi if x["typ"] == "bramy_garazowe"]
    wejsciowe = [x for x in drzwi if x["typ"] not in ("balkonowe_tarasowe", "bramy_garazowe")]
    przeszklenia = okna + balkonowe  # drzwi balkonowe liczone jak okna
    if przeszklenia:
        pow_ = [o["pow"] for o in przeszklenia]
        if u_bez_pow:  # okna bez podanej powierzchni — typowe okno średnie, do potwierdzenia
            pow_ += [cfg["zalozenia"]["pow_okna_srednie"]] * len(u_bez_pow)
            szacowane |= {"okna_male", "okna_srednie", "okna_duze"}
            pytaj(f"{len(u_bez_pow)} okien w audycie nie ma powierzchni — przyjęto po "
                  f"{cfg['zalozenia']['pow_okna_srednie']:g} m². Sprawdź.", ["okna_srednie"], "Okno")
        for k, v in _okna_w_kategorie(pow_).items():
            ustaw(k, v, ZRODLO_WYLICZONE, "Okna i drzwi balkonowe ze ścian elewacyjnych audytu")
        ustaw("okna_dachowe", 0, ZRODLO_WYLICZONE)
    else:  # bez żadnej powierzchni okien szacunek byłby zgadywaniem — liczbę okien podaje człowiek
        bez_pow = f" (wymienia {len(u_bez_pow)} okien, ale bez powierzchni)" if u_bez_pow else ""
        pytaj(f"Audyt nie podaje powierzchni okien{bez_pow} — wpisz liczbę okien (małe / średnie / duże).",
              ["okna_male", "okna_srednie", "okna_duze"], "Okno 1:" if u_bez_pow else "Ściana elewacyjna nr")
    u_okien = [o["U"][1] for o in przeszklenia if o["U"]] + [u[1] for u in u_bez_pow if u]
    if u_okien:
        ustaw("okna_U_reczne", round(st.mean(u_okien), 2), ZRODLO_WPROST,
              "Górna wartość Uw z audytu (katalogowa; program dolicza osadzenie)", szukaj="Okno 1:")
    elif przeszklenia:
        pytaj("Audyt nie podaje U okien — uzupełnij typ szyb i rok montażu.", ["okna_typ", "okna_rok"], "Okno 1:")
    if bramy:
        pytaj(f"Pominięto {len(bramy)} bram(y) garażowe ({sum(b['pow'] for b in bramy):g} m²) — garaż przyjęto jako "
              "nieogrzewany. Jeśli jest ogrzewany, dopisz bramę jako drzwi.", [], "bramy_garazowe")
    if wejsciowe:
        ustaw("drzwi_ilosc", len(wejsciowe), ZRODLO_WYLICZONE)
        sr = sum(x["pow"] for x in wejsciowe) / len(wejsciowe)
        ustaw("drzwi_szer", round(min(max(sr / 2.0, 0.6), 3.0), 2), ZRODLO_WYLICZONE, f"Średnio {sr:g} m² na drzwi (wys. 2 m)")
        ustaw("drzwi_wys", 2.0, ZRODLO_WYLICZONE)
        u_drzwi = [x["U"][1] for x in wejsciowe if x["U"]]
        if u_drzwi:
            ustaw("drzwi_U_reczne", round(st.mean(u_drzwi), 2), ZRODLO_WPROST, "Ud z audytu (program dolicza osadzenie)")
        else:
            ustaw("drzwi_rok", int(r["rok"]) if r["rok"] else None, ZRODLO_WYLICZONE,
                  "Audyt nie podaje U drzwi — przyjęto typowe dla roku budowy.")
            szacowane.add("drzwi_rok")
    else:
        pytaj("Audyt nie wymienia drzwi zewnętrznych w ścianach elewacyjnych — wpisz ich liczbę (0, jeśli brak).",
              ["drzwi_ilosc"], "Ściana elewacyjna nr")

    for k, zr in d.zrodla.items():
        if zr == ZRODLO_WYLICZONE and k not in szacowane:
            d.zrodla[k] = ZRODLO_PRZELICZONE

    podsumowanie = (f"Audyt komputerowy FlexiPower — odczytany bez AI. {len(el)} ścian elewacyjnych, "
                    f"{len(przeszklenia) + len(u_bez_pow)} okien/drzwi balkonowych"
                    + (f" (w tym {len(u_bez_pow)} bez powierzchni)" if u_bez_pow else "")
                    + f", {len(wejsciowe)} drzwi zewnętrznych.")
    return WynikOdczytu(uzupelnij_domyslne(d), pytania, podsumowanie)


def importuj(zawartosc: bytes) -> WynikOdczytu:
    strony = _Strony(zawartosc)
    return interpretuj(parsuj_tekst(strony.tekst), strony)
